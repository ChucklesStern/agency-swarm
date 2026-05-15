"""List all documents in a project."""

from agency_swarm.tools import BaseTool
from pydantic import Field

from .utils.doc_file_utils import get_project_dir, get_mnt_dir



class ListDocuments(BaseTool):
    """
    List all documents in a project folder.
    
    Shows all .source.html files (the canonical source) along with their
    associated .docx files and any converted formats (PDF, MD, TXT).
    
    Use this tool to:
    - See what documents exist in a project
    - Check file sizes and formats
    - Verify document creation
    - Browse available documents before reading/editing
    """
    
    project_name: str = Field(
        ...,
        description="Name of the project folder to list documents from"
    )

    def run(self):
        """List all documents in the project."""
        try:
            project_dir = get_project_dir(self.project_name)

            if not project_dir.exists():
                mnt_dir = get_mnt_dir()
                if mnt_dir.exists():
                    projects = [d.name for d in mnt_dir.iterdir() if d.is_dir() and (d / "documents").exists()]
                    if projects:
                        projects_list = "\n  - ".join(projects)
                        return f"""Error: Project '{self.project_name}' not found.

Available projects:
  - {projects_list}"""
                    else:
                        return f"""Error: Project '{self.project_name}' not found.

No projects exist yet. Create a document first using CreateDocument tool."""
                else:
                    return f"""Error: Project '{self.project_name}' not found.

No projects directory exists yet. Create a document first using CreateDocument tool."""
            
            source_files = list(project_dir.glob("*.source.html"))
            
            if not source_files:
                return f"""Project: {self.project_name}
Path: {project_dir}

No documents found in this project.

Use CreateDocument tool to create a new document."""
            
            documents = []

            for source_file in sorted(source_files):
                doc_name = source_file.name.replace(".source.html", "")
                lines = [f"  {len(documents) + 1}. {doc_name}"]
                lines.append(f"    Source: {source_file.name} ({source_file.stat().st_size:,} bytes)")

                # All DOCX exports: base + versioned (_v2, _v3, …), skip Word lock files (~$…)
                docx_exports = sorted(
                    f for f in project_dir.glob(f"{doc_name}*.docx")
                    if not f.name.startswith("~$")
                )
                if docx_exports:
                    lines.append("    Exports:")
                    for docx in docx_exports:
                        snapshot = project_dir / f"{docx.name}.snapshot.html"
                        snapshot_flag = " [snapshot]" if snapshot.exists() else ""
                        lines.append(
                            f"      - {docx.name} ({docx.stat().st_size:,} bytes){snapshot_flag}"
                        )
                else:
                    lines.append("    Exports: none (use ConvertDocument to generate)")

                # Other converted formats (PDF, MD, TXT)
                others = []
                for ext, label in [(".pdf", "PDF"), (".md", "Markdown"), (".txt", "TXT")]:
                    f = project_dir / f"{doc_name}{ext}"
                    if f.exists():
                        others.append(f"{label} ({f.stat().st_size:,} bytes)")
                if others:
                    lines.append(f"    Other formats: {', '.join(others)}")

                documents.append("\n".join(lines))

            return (
                f"Project: {self.project_name}\n"
                f"Path: {project_dir}\n\n"
                f"Documents ({len(documents)}):\n\n"
                + "\n\n".join(documents)
            )
            
        except Exception as e:
            return f"Error listing documents: {str(e)}"


if __name__ == "__main__":
    print("=" * 70)
    print("TEST: ListDocuments Tool")
    print("=" * 70)
    print()
    
    print("Setup: Creating test documents...")
    
    # Test 1: List documents in project
    print("Test 1: Listing documents in test_list project...")
    tool = ListDocuments(project_name="test_list")
    print(tool.run())
    print()
    
    # Test 2: List documents in non-existent project
    print("Test 2: Attempting to list non-existent project...")
    tool = ListDocuments(project_name="nonexistent_project")
    print(tool.run())
    print()
    
    # Test 3: List documents in empty project
    print("Test 3: Listing documents in empty project...")
    empty_dir = get_project_dir("empty_project")
    empty_dir.mkdir(parents=True, exist_ok=True)
    
    tool = ListDocuments(project_name="empty_project")
    print(tool.run())
