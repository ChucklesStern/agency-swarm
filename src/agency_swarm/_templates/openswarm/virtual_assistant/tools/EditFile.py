import os
from typing import Optional

from agency_swarm.tools import BaseTool
from pydantic import Field


class EditFile(BaseTool):
    """
    Performs exact string replacements in files.

    Usage:
    - You must use ReadFile tool at least once in the conversation before editing.
    - When editing text, preserve the exact indentation (tabs/spaces) as it appears in the file.
    - The edit will FAIL if old_string is not unique in the file. Provide more context to make it unique or use replace_all.
    - Use replace_all for replacing and renaming strings across the file.
    """

    file_path: str = Field(..., description="The absolute path to the file to modify")
    old_string: str = Field(..., description="The text to replace")
    new_string: str = Field(
        ...,
        description="The text to replace it with (must be different from old_string)",
    )
    replace_all: Optional[bool] = Field(
        False, description="Replace all occurrences of old_string (default false)"
    )

    def run(self):
        try:
            if self.old_string == self.new_string:
                return "Error: old_string and new_string must be different"

            if not os.path.exists(self.file_path):
                return f"Error: File does not exist: {self.file_path}"

            if not os.path.isfile(self.file_path):
                return f"Error: Path is not a file: {self.file_path}"

            try:
                with open(self.file_path, "r", encoding="utf-8") as file:
                    content = file.read()
            except UnicodeDecodeError:
                return f"Error: Unable to decode file {self.file_path}. It may be a binary file."

            if self.old_string not in content:
                return f"Error: String to replace not found in file.\nString: {repr(self.old_string)}"

            occurrences = content.count(self.old_string)

            if occurrences > 1 and not self.replace_all:
                previews = []
                start_idx = 0
                for _ in range(2):
                    idx = content.find(self.old_string, start_idx)
                    if idx == -1:
                        break
                    a = max(0, idx - 30)
                    b = min(len(content), idx + len(self.old_string) + 30)
                    previews.append("..." + content[a:b] + "...")
                    start_idx = idx + len(self.old_string)
                preview_block = "\n".join(previews)
                return (
                    f"Error: String appears {occurrences} times in file. Either provide a larger string with more "
                    f"surrounding context to make it unique or use replace_all=True to change every instance.\n"
                    f"First matches:\n{preview_block}"
                )

            if self.replace_all:
                new_content = content.replace(self.old_string, self.new_string)
                replacement_count = occurrences
            else:
                new_content = content.replace(self.old_string, self.new_string, 1)
                replacement_count = 1

            try:
                with open(self.file_path, "w", encoding="utf-8") as file:
                    file.write(new_content)
                return f"Successfully replaced {replacement_count} occurrence(s) in {self.file_path}"
            except PermissionError:
                return f"Error: Permission denied writing to file: {self.file_path}"
            except Exception as e:
                return f"Error writing to file: {str(e)}"

        except Exception as e:
            return f"Error during edit operation: {str(e)}"


if __name__ == "__main__":
    # Test the tool
    test_file_path = "/tmp/test_edit_tool.txt"
    test_content = """This is a test file.
Line 2 has some text.
Line 3 has the same text.
Final line."""

    # Create test file
    with open(test_file_path, "w") as f:
        f.write(test_content)

    print("Original content:")
    print(test_content)
    print("\n" + "=" * 50 + "\n")

    tool = EditFile(
        file_path=test_file_path, old_string="some text", new_string="REPLACED TEXT"
    )
    result = tool.run()
    print(result)

    # Cleanup
    os.remove(test_file_path)

