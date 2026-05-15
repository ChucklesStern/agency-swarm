import os

from agency_swarm.tools import BaseTool
from pydantic import Field


class WriteFile(BaseTool):
    """
    Writes a file to the local filesystem.

    Usage:
    - This tool will overwrite the existing file if there is one at the provided path.
    - If this is an existing file, you MUST use the ReadFile tool first to read the file's contents.
    - The file_path must be an absolute path.
    """

    file_path: str = Field(
        ...,
        description="Absolute path to the file to write.",
    )
    content: str = Field(..., description="The content to write to the file")

    def run(self):
        try:
            if not os.path.isabs(self.file_path):
                return f"Error: File path must be absolute: {self.file_path}"

            file_exists = os.path.exists(self.file_path)

            if file_exists:
                if not os.path.isfile(self.file_path):
                    return f"Error: Path exists but is not a file: {self.file_path}"
                operation = "overwritten"
            else:
                directory = os.path.dirname(self.file_path)
                if directory and not os.path.exists(directory):
                    try:
                        os.makedirs(directory, exist_ok=True)
                    except Exception as e:
                        return f"Error creating directory {directory}: {str(e)}"
                operation = "created"

            try:
                with open(self.file_path, "w", encoding="utf-8") as file:
                    file.write(self.content)

                file_size = os.path.getsize(self.file_path)
                line_count = self.content.count("\n") + (
                    1 if self.content and not self.content.endswith("\n") else 0
                )

                abs_path = os.path.abspath(self.file_path)
                try:
                    if hasattr(self, '_context') and self._context is not None:
                        read_files = self._context.get("read_files", set())
                        read_files.add(abs_path)
                        self._context.set("read_files", read_files)
                except (AttributeError, TypeError):
                    pass

                return f"Successfully {operation} file: {self.file_path}\nSize: {file_size} bytes, Lines: {line_count}"

            except PermissionError:
                return f"Error: Permission denied writing to file: {self.file_path}"
            except Exception as e:
                return f"Error writing file: {str(e)}"

        except Exception as e:
            return f"Error during write operation: {str(e)}"


if __name__ == "__main__":
    # Test the tool
    test_file_path = "/tmp/test_write_tool.py"
    test_content = '''#!/usr/bin/env python3
"""Test Python file created by WriteFile tool."""

def hello_world():
    print("Hello, World!")
    return True

if __name__ == "__main__":
    hello_world()
'''

    tool = WriteFile(file_path=test_file_path, content=test_content)
    result = tool.run()
    print("Write result:")
    print(result)

    # Cleanup
    if os.path.exists(test_file_path):
        os.remove(test_file_path)
        print("\nTest file cleaned up.")

