#!/usr/bin/env python3
"""
Example of using the AMBER MCP server directly
"""

import asyncio
import json
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_amber_relax():
    """Test AMBER PDB relaxation functionality"""
    # Create server parameters
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "src.server"],
        env={
            "BIO_MCP_TIMEOUT": "3600",  # 1 hour timeout for MD
            "BIO_MCP_TLEAP_PATH": "tleap",
            "BIO_MCP_PMEMD_PATH": "pmemd"
        }
    )
    
    # Connect to server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print("Available AMBER tools:")
            for tool in tools:
                print(f"  - {tool.name}: {tool.description}")
            print()
            
            # Example 1: Prepare a PDB system
            print("=== Preparing PDB system ===")
            try:
                result = await session.call_tool(
                    "amber_prepare_system",
                    {
                        "input_file": "example_data/protein.pdb",
                        "force_field": "ff19SB",
                        "water_model": "tip3p"
                    }
                )
                
                print("System preparation result:")
                for content in result:
                    if hasattr(content, 'text'):
                        print(content.text)
                    else:
                        print(f"Error: {content}")
                print()
            except Exception as e:
                print(f"System preparation failed: {e}")
                print()
            
            # Example 2: Relax PDB structure
            print("=== Relaxing PDB structure ===")
            try:
                result = await session.call_tool(
                    "amber_relax_pdb",
                    {
                        "input_file": "example_data/protein.pdb",
                        "force_field": "ff19SB",
                        "steps": 10000,
                        "restraints": True
                    }
                )
                
                print("PDB relaxation result:")
                for content in result:
                    if hasattr(content, 'text'):
                        print(content.text[:1000])  # Print first 1000 chars
                        if len(content.text) > 1000:
                            print("... (truncated)")
                    else:
                        print(f"Error: {content}")
                        
            except Exception as e:
                print(f"PDB relaxation failed: {e}")


async def create_sample_pdb():
    """Create a sample PDB file for testing"""
    sample_pdb = """ATOM      1  N   ALA A   1      20.154  16.967  18.587  1.00 16.77           N  
ATOM      2  CA  ALA A   1      18.744  16.522  18.587  1.00 16.57           C  
ATOM      3  C   ALA A   1      17.905  17.007  17.395  1.00 16.57           C  
ATOM      4  O   ALA A   1      18.169  16.811  16.206  1.00 16.16           O  
ATOM      5  CB  ALA A   1      18.136  16.940  19.918  1.00 16.29           C  
ATOM      6  N   GLY A   2      16.805  17.642  17.618  1.00 16.57           N  
ATOM      7  CA  GLY A   2      15.917  18.200  16.618  1.00 16.16           C  
ATOM      8  C   GLY A   2      15.117  19.346  17.220  1.00 15.85           C  
ATOM      9  O   GLY A   2      14.775  19.267  18.402  1.00 15.85           O  
ATOM     10  N   ALA A   3      14.834  20.413  16.475  1.00 15.85           N  
ATOM     11  CA  ALA A   3      14.072  21.585  16.897  1.00 15.85           C  
ATOM     12  C   ALA A   3      13.214  22.135  15.758  1.00 15.85           C  
ATOM     13  O   ALA A   3      13.519  22.051  14.572  1.00 15.85           O  
ATOM     14  CB  ALA A   3      14.917  22.667  17.543  1.00 15.85           C  
END
"""
    
    # Create example data directory
    example_dir = Path("example_data")
    example_dir.mkdir(exist_ok=True)
    
    # Write sample PDB
    pdb_file = example_dir / "protein.pdb"
    pdb_file.write_text(sample_pdb)
    print(f"Created sample PDB file: {pdb_file}")


async def main():
    """Main function to run examples"""
    print("AMBER MCP Server Example Usage")
    print("=" * 40)
    
    # Create sample data
    await create_sample_pdb()
    print()
    
    # Test AMBER functionality
    await test_amber_relax()


if __name__ == "__main__":
    asyncio.run(main())