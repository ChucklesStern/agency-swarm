import os

from agency_swarm.tools import BaseTool


class ListSkills(BaseTool):
    """
    Lists all skills currently available to you.
    """

    def run(self):
        try:
            skills_path = os.path.join(os.getcwd(), "mnt/skills")

            if not os.path.exists(skills_path):
                return f"Error: Skills folder does not exist: {skills_path}"

            if not os.path.isdir(skills_path):
                return f"Error: Skills path is not a directory: {skills_path}"

            skills = []
            try:
                entries = os.listdir(skills_path)
            except PermissionError:
                return f"Error: Permission denied accessing skills folder: {skills_path}"

            for entry in sorted(entries):
                entry_path = os.path.join(skills_path, entry)

                if not os.path.isdir(entry_path):
                    continue

                skill_file = None
                if os.path.exists(os.path.join(entry_path, "SKILL.md")):
                    skill_file = os.path.join(entry_path, "SKILL.md")
                elif os.path.exists(os.path.join(entry_path, "skill.md")):
                    skill_file = os.path.join(entry_path, "skill.md")

                if not skill_file:
                    continue

                try:
                    with open(skill_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    name = None
                    description = None

                    # Parse frontmatter: lines 2 and 3 carry "name:" and "description:"
                    if len(lines) > 1:
                        line2 = lines[1].strip()
                        if line2.startswith("name:"):
                            name = line2.split("name:", 1)[1].strip()

                    if len(lines) > 2:
                        line3 = lines[2].strip()
                        if line3.startswith("description:"):
                            description = line3.split("description:", 1)[1].strip()

                    skills.append({
                        "name": name or entry,
                        "description": description or "No description available",
                        "relative_path": os.path.relpath(skill_file, os.getcwd()),
                    })

                except Exception as e:
                    skills.append({
                        "name": entry,
                        "description": f"Error reading skill file: {str(e)}",
                        "relative_path": os.path.relpath(skill_file, os.getcwd()),
                    })

            if not skills:
                return f"No skills found in {skills_path}"

            output = [f"Found {len(skills)} skill(s) in {skills_path}:\n"]

            for i, skill in enumerate(skills, 1):
                output.append(f"\n{i}. {skill['name']}")
                output.append(f"   Description: {skill['description']}")
                output.append(f"   Path: {skill['relative_path']}")

            return "\n".join(output)

        except Exception as e:
            return f"Error listing skills: {str(e)}"


if __name__ == "__main__":
    # Test the tool
    tool = ListSkills()
    result = tool.run()
    print(result)

