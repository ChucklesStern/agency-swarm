from typing import Literal, Optional
from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from helpers import execute_composio_tool


class ManageLabels(BaseTool):
    """
    Manages email labels (Gmail) or categories (Outlook).
    
    Actions:
    - list: List all labels/categories
    - create: Create a new label/category
    - update: Rename or update a label (Gmail only)
    - delete: Delete a label/category
    """
    
    provider: Literal["gmail", "outlook"] = Field(
        ...,
        description="Email provider: 'gmail' or 'outlook'"
    )
    
    action: Literal["list", "create", "update", "delete"] = Field(
        ...,
        description="Action to perform: 'list', 'create', 'update', or 'delete'"
    )
    
    label_name: Optional[str] = Field(
        default=None,
        description="Name of the label/category (required for create, update)"
    )
    
    label_id: Optional[str] = Field(
        default=None,
        description="ID of the label/category (required for update, delete). For Gmail, use format 'Label_123'"
    )
    
    new_name: Optional[str] = Field(
        default=None,
        description="New name when updating a label (Gmail only)"
    )
    
    color: Optional[str] = Field(
        default=None,
        description="Color for the label. Gmail: hex color like '#fb4c2f'. Outlook: 'preset0' through 'preset24'"
    )
    
    def run(self):
        try:
            if self.provider == "gmail":
                return self._manage_gmail_labels(execute_composio_tool)
            else:
                return self._manage_outlook_categories(execute_composio_tool)
                
        except Exception as e:
            return f"Error managing labels: {str(e)}"
    
    def _manage_gmail_labels(self, execute_tool) -> str:
        """Manages Gmail labels."""
        if self.action == "list":
            return self._list_gmail_labels(execute_tool)
        elif self.action == "create":
            return self._create_gmail_label(execute_tool)
        elif self.action == "update":
            return self._update_gmail_label(execute_tool)
        elif self.action == "delete":
            return self._delete_gmail_label(execute_tool)
        else:
            return f"Unknown action: {self.action}"
    
    def _list_gmail_labels(self, execute_tool) -> str:
        """Lists all Gmail labels."""
        result = execute_tool(
            tool_name="GMAIL_LIST_LABELS",
            arguments={"user_id": "me"},
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error listing Gmail labels: {result.get('error')}"
        
        labels = result.get("data", {}).get("labels", [])
        
        formatted_labels = []
        for label in labels:
            formatted_labels.append({
                "id": label.get("id"),
                "name": label.get("name"),
                "type": label.get("type"),  # system or user
            })
        
        return json.dumps({
            "provider": "gmail",
            "count": len(formatted_labels),
            "labels": formatted_labels
        }, indent=2)
    
    def _create_gmail_label(self, execute_tool) -> str:
        """Creates a Gmail label."""
        if not self.label_name:
            return "Error: label_name is required for create action"
        
        arguments = {
            "user_id": "me",
            "label_name": self.label_name
        }
        
        if self.color:
            arguments["background_color"] = self.color
        
        result = execute_tool(
            tool_name="GMAIL_CREATE_LABEL",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error creating Gmail label: {result.get('error')}"
        
        data = result.get("data", {})
        
        return json.dumps({
            "provider": "gmail",
            "success": True,
            "action": "create",
            "label_id": data.get("id"),
            "label_name": data.get("name")
        }, indent=2)
    
    def _update_gmail_label(self, execute_tool) -> str:
        """Updates a Gmail label."""
        if not self.label_id:
            return "Error: label_id is required for update action"
        
        arguments = {
            "userId": "me",
            "id": self.label_id
        }
        
        if self.new_name:
            arguments["name"] = self.new_name
        
        if self.color:
            arguments["color"] = {
                "backgroundColor": self.color,
                "textColor": "#ffffff"
            }
        
        if not self.new_name and not self.color:
            return "Error: new_name or color is required for update action"
        
        result = execute_tool(
            tool_name="GMAIL_PATCH_LABEL",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error updating Gmail label: {result.get('error')}"
        
        data = result.get("data", {})
        
        return json.dumps({
            "provider": "gmail",
            "success": True,
            "action": "update",
            "label_id": data.get("id"),
            "label_name": data.get("name")
        }, indent=2)
    
    def _delete_gmail_label(self, execute_tool) -> str:
        """Deletes a Gmail label."""
        if not self.label_id:
            return "Error: label_id is required for delete action"
        
        result = execute_tool(
            tool_name="GMAIL_DELETE_LABEL",
            arguments={
                "user_id": "me",
                "label_id": self.label_id
            },
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error deleting Gmail label: {result.get('error')}"
        
        return json.dumps({
            "provider": "gmail",
            "success": True,
            "action": "delete",
            "label_id": self.label_id
        }, indent=2)
    
    def _manage_outlook_categories(self, execute_tool) -> str:
        """Manages Outlook categories."""
        if self.action == "list":
            return self._list_outlook_categories(execute_tool)
        elif self.action == "create":
            return self._create_outlook_category(execute_tool)
        elif self.action == "update":
            return "Error: Outlook categories cannot be renamed via API. Delete and recreate instead."
        elif self.action == "delete":
            return "Error: Outlook category deletion not available. Categories can only be managed in Outlook settings."
        else:
            return f"Unknown action: {self.action}"
    
    def _list_outlook_categories(self, execute_tool) -> str:
        """Lists all Outlook categories."""
        result = execute_tool(
            tool_name="OUTLOOK_GET_MASTER_CATEGORIES",
            arguments={"user_id": "me"},
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error listing Outlook categories: {result.get('error')}"
        
        categories = result.get("data", {}).get("value", [])
        
        formatted_categories = []
        for cat in categories:
            formatted_categories.append({
                "id": cat.get("id"),
                "name": cat.get("displayName"),
                "color": cat.get("color")
            })
        
        return json.dumps({
            "provider": "outlook",
            "count": len(formatted_categories),
            "categories": formatted_categories
        }, indent=2)
    
    def _create_outlook_category(self, execute_tool) -> str:
        """Creates an Outlook category."""
        if not self.label_name:
            return "Error: label_name is required for create action"
        
        arguments = {"displayName": self.label_name}
        
        if self.color:
            arguments["color"] = self.color
        
        result = execute_tool(
            tool_name="OUTLOOK_CREATE_MASTER_CATEGORY",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error creating Outlook category: {result.get('error')}"
        
        data = result.get("data", {})
        
        return json.dumps({
            "provider": "outlook",
            "success": True,
            "action": "create",
            "category_id": data.get("id"),
            "category_name": data.get("displayName"),
            "color": data.get("color")
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("=" * 60)
    print("ManageLabels Test Suite")
    print("=" * 60)
    print()
    
    # Test 1: List Gmail labels
    print("Test 1: List Gmail labels")
    print("-" * 60)
    tool = ManageLabels(provider="gmail", action="list")
    result = tool.run()
    # Just show first few labels
    import json
    data = json.loads(result)
    data["labels"] = data["labels"][:5]
    print(json.dumps(data, indent=2))
    print()
    
    # Test 2: List Outlook categories
    print("Test 2: List Outlook categories")
    print("-" * 60)
    tool = ManageLabels(provider="outlook", action="list")
    result = tool.run()
    print(result)
    print()
    
    print("=" * 60)
    print("Tests completed!")
    print("=" * 60)

