import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, ErrorData
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings


logger = logging.getLogger(__name__)


class ServerSettings(BaseSettings):
    max_file_size: int = Field(default=100_000_000, description="Maximum input file size in bytes")
    temp_dir: Optional[str] = Field(default=None, description="Temporary directory for processing")
    timeout: int = Field(default=1800, description="Command timeout in seconds (30 minutes for MD)")
    amber_path: str = Field(default="amber", description="Path to amber installation")
    tleap_path: str = Field(default="tleap", description="Path to tleap executable")
    pmemd_path: str = Field(default="pmemd", description="Path to pmemd executable")
    
    model_config = ConfigDict(env_prefix="BIO_MCP_")


class AmberServer:
    def __init__(self, settings: Optional[ServerSettings] = None):
        self.settings = settings or ServerSettings()
        self.server = Server("bio-mcp-amber")
        self._setup_handlers()
        
    def _setup_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="amber_relax_pdb",
                    description="Perform energy minimization and relaxation of PDB structures using AMBER",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "input_file": {
                                "type": "string", 
                                "description": "Path to input PDB file"
                            },
                            "force_field": {
                                "type": "string",
                                "description": "Force field to use (default: ff19SB)",
                                "default": "ff19SB"
                            },
                            "steps": {
                                "type": "integer",
                                "description": "Number of minimization steps (default: 10000)",
                                "default": 10000
                            },
                            "restraints": {
                                "type": "boolean",
                                "description": "Apply positional restraints to backbone atoms (default: false)",
                                "default": False
                            }
                        },
                        "required": ["input_file"]
                    }
                ),
                Tool(
                    name="amber_prepare_system",
                    description="Prepare a PDB structure for AMBER simulation by adding hydrogens and parameters",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "input_file": {
                                "type": "string",
                                "description": "Path to input PDB file"
                            },
                            "force_field": {
                                "type": "string",
                                "description": "Force field to use (default: ff19SB)",
                                "default": "ff19SB"
                            },
                            "water_model": {
                                "type": "string",
                                "description": "Water model to use (default: tip3p)",
                                "default": "tip3p"
                            }
                        },
                        "required": ["input_file"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent | ImageContent | ErrorData]:
            if name == "amber_relax_pdb":
                return await self._relax_pdb(arguments)
            elif name == "amber_prepare_system":
                return await self._prepare_system(arguments)
            else:
                return [ErrorData(code=500, message=f"Unknown tool: {name}")]
    
    async def _relax_pdb(self, arguments: dict) -> list[TextContent | ErrorData]:
        try:
            # Validate input file
            input_path = Path(arguments["input_file"])
            if not input_path.exists():
                return [ErrorData(code=404, message=f"Input file not found: {input_path}")]
            
            if input_path.stat().st_size > self.settings.max_file_size:
                return [ErrorData(code=413, message=f"File too large. Maximum size: {self.settings.max_file_size} bytes")]
            
            force_field = arguments.get("force_field", "ff19SB")
            steps = arguments.get("steps", 10000)
            restraints = arguments.get("restraints", False)
            
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory(dir=self.settings.temp_dir) as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Copy input file to temp directory
                temp_input = tmpdir_path / input_path.name
                temp_input.write_bytes(input_path.read_bytes())
                
                # Step 1: Prepare the system with tleap
                prep_result = await self._prepare_system_internal(tmpdir_path, temp_input, force_field, "tip3p")
                if not prep_result["success"]:
                    return [ErrorData(code=500, message=f"System preparation failed: {prep_result['error']}")]
                
                # Step 2: Run energy minimization
                min_result = await self._run_minimization(tmpdir_path, steps, restraints)
                if not min_result["success"]:
                    return [ErrorData(code=500, message=f"Minimization failed: {min_result['error']}")]
                
                # Read output files
                output_pdb = tmpdir_path / "minimized.pdb"
                output_log = tmpdir_path / "minimization.log"
                
                result_text = f"AMBER PDB relaxation completed successfully!\n\n"
                result_text += f"Force field: {force_field}\n"
                result_text += f"Minimization steps: {steps}\n"
                result_text += f"Restraints applied: {restraints}\n\n"
                
                if output_log.exists():
                    result_text += "Minimization log:\n"
                    result_text += output_log.read_text()
                    result_text += "\n\n"
                
                if output_pdb.exists():
                    result_text += f"Relaxed structure saved to: {output_pdb}\n"
                    result_text += f"Final structure coordinates:\n"
                    result_text += output_pdb.read_text()[:2000]  # First 2000 chars
                    if len(output_pdb.read_text()) > 2000:
                        result_text += "\n... (truncated)"
                
                return [TextContent(type="text", text=result_text)]
                
        except Exception as e:
            logger.error(f"Error running AMBER relaxation: {e}", exc_info=True)
            return [ErrorData(code=500, message=f"Error: {str(e)}")]
    
    async def _prepare_system(self, arguments: dict) -> list[TextContent | ErrorData]:
        try:
            # Validate input file
            input_path = Path(arguments["input_file"])
            if not input_path.exists():
                return [ErrorData(code=404, message=f"Input file not found: {input_path}")]
            
            if input_path.stat().st_size > self.settings.max_file_size:
                return [ErrorData(code=413, message=f"File too large. Maximum size: {self.settings.max_file_size} bytes")]
            
            force_field = arguments.get("force_field", "ff19SB")
            water_model = arguments.get("water_model", "tip3p")
            
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory(dir=self.settings.temp_dir) as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Copy input file to temp directory
                temp_input = tmpdir_path / input_path.name
                temp_input.write_bytes(input_path.read_bytes())
                
                # Prepare the system
                result = await self._prepare_system_internal(tmpdir_path, temp_input, force_field, water_model)
                
                if not result["success"]:
                    return [ErrorData(code=500, message=f"System preparation failed: {result['error']}")]
                
                # Read output files
                output_text = f"AMBER system preparation completed successfully!\n\n"
                output_text += f"Force field: {force_field}\n"
                output_text += f"Water model: {water_model}\n\n"
                output_text += f"tleap log:\n{result['log']}\n\n"
                
                # Check for generated files
                prmtop_file = tmpdir_path / "system.prmtop"
                inpcrd_file = tmpdir_path / "system.inpcrd"
                
                if prmtop_file.exists():
                    output_text += f"Parameter file generated: system.prmtop ({prmtop_file.stat().st_size} bytes)\n"
                if inpcrd_file.exists():
                    output_text += f"Coordinate file generated: system.inpcrd ({inpcrd_file.stat().st_size} bytes)\n"
                
                return [TextContent(type="text", text=output_text)]
                
        except Exception as e:
            logger.error(f"Error preparing AMBER system: {e}", exc_info=True)
            return [ErrorData(code=500, message=f"Error: {str(e)}")]
    
    async def _prepare_system_internal(self, tmpdir: Path, pdb_file: Path, force_field: str, water_model: str) -> dict:
        """Internal method to prepare AMBER system using tleap"""
        try:
            # Create tleap script
            tleap_script = tmpdir / "prep.leap"
            script_content = f"""source leaprc.protein.{force_field}
source leaprc.water.{water_model}

# Load the PDB structure
mol = loadpdb {pdb_file.name}

# Add hydrogens and prepare the system
mol = addions mol Na+ 0
mol = addions mol Cl- 0

# Save parameter and coordinate files
saveamberparm mol system.prmtop system.inpcrd

# Save as PDB for visualization
savepdb mol prepared.pdb

quit
"""
            tleap_script.write_text(script_content)
            
            # Run tleap
            cmd = [self.settings.tleap_path, "-f", str(tleap_script)]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.settings.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return {"success": False, "error": f"tleap timed out after {self.settings.timeout} seconds"}
            
            if process.returncode != 0:
                return {"success": False, "error": f"tleap failed: {stderr.decode()}"}
            
            return {"success": True, "log": stdout.decode()}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _run_minimization(self, tmpdir: Path, steps: int, restraints: bool) -> dict:
        """Internal method to run AMBER energy minimization"""
        try:
            # Create minimization input file
            min_input = tmpdir / "min.in"
            input_content = f"""Energy minimization
&cntrl
  imin=1,       ! Minimize energy
  maxcyc={steps}, ! Maximum cycles
  ncyc={steps//2}, ! Initial steepest descent steps
  ntb=0,        ! No periodic boundaries
  cut=999.0,    ! No cutoff
"""
            if restraints:
                input_content += "  ntr=1,        ! Apply restraints\n"
                input_content += "  restraint_wt=10.0, ! Restraint weight\n"
                input_content += "  restraintmask='@CA,C,N', ! Restrain backbone atoms\n"
            
            input_content += "&end\n"
            min_input.write_text(input_content)
            
            # Create restraint file if needed
            if restraints:
                rst_file = tmpdir / "restraints.rst"
                rst_content = """Hold backbone atoms fixed
10.0
RES 1 999
END
END
"""
                rst_file.write_text(rst_content)
            
            # Run pmemd for minimization
            cmd = [
                self.settings.pmemd_path,
                "-O",
                "-i", "min.in",
                "-o", "minimization.log",
                "-p", "system.prmtop",
                "-c", "system.inpcrd",
                "-r", "minimized.rst",
                "-ref", "system.inpcrd"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.settings.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return {"success": False, "error": f"Minimization timed out after {self.settings.timeout} seconds"}
            
            if process.returncode != 0:
                return {"success": False, "error": f"pmemd failed: {stderr.decode()}"}
            
            # Convert final structure to PDB
            await self._convert_to_pdb(tmpdir)
            
            return {"success": True, "log": stdout.decode()}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _convert_to_pdb(self, tmpdir: Path) -> None:
        """Convert AMBER restart file to PDB format using cpptraj"""
        try:
            # Create cpptraj script
            cpptraj_script = tmpdir / "convert.cpptraj"
            script_content = """parm system.prmtop
trajin minimized.rst
trajout minimized.pdb pdb
run
quit
"""
            cpptraj_script.write_text(script_content)
            
            # Run cpptraj
            cmd = ["cpptraj", "-i", "convert.cpptraj"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir
            )
            
            await process.communicate()
            
        except Exception as e:
            logger.warning(f"Failed to convert to PDB: {e}")
    
    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream)


async def main():
    logging.basicConfig(level=logging.INFO)
    server = AmberServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())