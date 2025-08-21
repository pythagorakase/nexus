from typing import Any, Dict, List, Optional

from pydantic import Field, model_validator

from letta.constants import (
    COMPOSIO_TOOL_TAG_NAME,
    FUNCTION_RETURN_CHAR_LIMIT,
    LETTA_BUILTIN_TOOL_MODULE_NAME,
    LETTA_CORE_TOOL_MODULE_NAME,
    LETTA_FILES_TOOL_MODULE_NAME,
    LETTA_MULTI_AGENT_TOOL_MODULE_NAME,
    LETTA_VOICE_TOOL_MODULE_NAME,
    MCP_TOOL_TAG_NAME_PREFIX,
)
from letta.functions.ast_parsers import get_function_name_and_docstring
from letta.functions.composio_helpers import generate_composio_tool_wrapper
from letta.functions.functions import derive_openai_json_schema, get_json_schema_from_module
from letta.functions.mcp_client.types import MCPTool
from letta.functions.schema_generator import (
    generate_schema_from_args_schema_v2,
    generate_tool_schema_for_composio,
    generate_tool_schema_for_mcp,
)
from letta.log import get_logger
from letta.schemas.enums import ToolType
from letta.schemas.letta_base import LettaBase
from letta.schemas.npm_requirement import NpmRequirement
from letta.schemas.pip_requirement import PipRequirement

logger = get_logger(__name__)


class BaseTool(LettaBase):
    __id_prefix__ = "tool"


class Tool(BaseTool):
    """
    Representation of a tool, which is a function that can be called by the agent.

    Parameters:
        id (str): The unique identifier of the tool.
        name (str): The name of the function.
        tags (List[str]): Metadata tags.
        source_code (str): The source code of the function.
        json_schema (Dict): The JSON schema of the function.

    """

    id: str = BaseTool.generate_id_field()
    tool_type: ToolType = Field(ToolType.CUSTOM, description="The type of the tool.")
    description: Optional[str] = Field(None, description="The description of the tool.")
    source_type: Optional[str] = Field(None, description="The type of the source code.")
    name: Optional[str] = Field(None, description="The name of the function.")
    tags: List[str] = Field([], description="Metadata tags.")

    # code
    source_code: Optional[str] = Field(None, description="The source code of the function.")
    json_schema: Optional[Dict] = Field(None, description="The JSON schema of the function.")
    args_json_schema: Optional[Dict] = Field(None, description="The args JSON schema of the function.")

    # tool configuration
    return_char_limit: int = Field(FUNCTION_RETURN_CHAR_LIMIT, description="The maximum number of characters in the response.")
    pip_requirements: list[PipRequirement] | None = Field(None, description="Optional list of pip packages required by this tool.")
    npm_requirements: list[NpmRequirement] | None = Field(None, description="Optional list of npm packages required by this tool.")

    # metadata fields
    created_by_id: Optional[str] = Field(None, description="The id of the user that made this Tool.")
    last_updated_by_id: Optional[str] = Field(None, description="The id of the user that made this Tool.")
    metadata_: Optional[Dict[str, Any]] = Field(default_factory=dict, description="A dictionary of additional metadata for the tool.")

    @model_validator(mode="after")
    def refresh_source_code_and_json_schema(self):
        """
        Refresh name, description, source_code, and json_schema.
        """
        from letta.functions.helpers import generate_model_from_args_json_schema

        if self.tool_type is ToolType.CUSTOM:
            if not self.source_code:
                logger.error("Custom tool with id=%s is missing source_code field", self.id)
                raise ValueError(f"Custom tool with id={self.id} is missing source_code field.")

            # Always derive json_schema for freshest possible json_schema
            if self.args_json_schema is not None:
                name, description = get_function_name_and_docstring(self.source_code, self.name)
                args_schema = generate_model_from_args_json_schema(self.args_json_schema)
                self.json_schema = generate_schema_from_args_schema_v2(
                    args_schema=args_schema,
                    name=name,
                    description=description,
                    append_heartbeat=False,
                )
            else:  # elif not self.json_schema: # TODO: JSON schema is not being derived correctly the first time?
                # If there's not a json_schema provided, then we need to re-derive
                try:
                    self.json_schema = derive_openai_json_schema(source_code=self.source_code)
                except Exception as e:
                    logger.error("Failed to derive json schema for tool with id=%s name=%s: %s", self.id, self.name, e)
        elif self.tool_type in {ToolType.LETTA_CORE, ToolType.LETTA_MEMORY_CORE, ToolType.LETTA_SLEEPTIME_CORE}:
            # If it's letta core tool, we generate the json_schema on the fly here
            self.json_schema = get_json_schema_from_module(module_name=LETTA_CORE_TOOL_MODULE_NAME, function_name=self.name)
        elif self.tool_type in {ToolType.LETTA_MULTI_AGENT_CORE}:
            # If it's letta multi-agent tool, we also generate the json_schema on the fly here
            self.json_schema = get_json_schema_from_module(module_name=LETTA_MULTI_AGENT_TOOL_MODULE_NAME, function_name=self.name)
        elif self.tool_type in {ToolType.LETTA_VOICE_SLEEPTIME_CORE}:
            # If it's letta voice tool, we generate the json_schema on the fly here
            self.json_schema = get_json_schema_from_module(module_name=LETTA_VOICE_TOOL_MODULE_NAME, function_name=self.name)
        elif self.tool_type in {ToolType.LETTA_BUILTIN}:
            # If it's letta voice tool, we generate the json_schema on the fly here
            self.json_schema = get_json_schema_from_module(module_name=LETTA_BUILTIN_TOOL_MODULE_NAME, function_name=self.name)
        elif self.tool_type in {ToolType.LETTA_FILES_CORE}:
            # If it's letta files tool, we generate the json_schema on the fly here
            self.json_schema = get_json_schema_from_module(module_name=LETTA_FILES_TOOL_MODULE_NAME, function_name=self.name)
        elif self.tool_type in {ToolType.EXTERNAL_COMPOSIO}:
            # Composio schemas handled separately
            pass

        # At this point, we need to validate that at least json_schema is populated
        if not self.json_schema:
            logger.error("Tool with id=%s name=%s tool_type=%s is missing a json_schema", self.id, self.name, self.tool_type)
            raise ValueError(f"Tool with id={self.id} name={self.name} tool_type={self.tool_type} is missing a json_schema.")

        # Derive name from the JSON schema if not provided
        if not self.name:
            # TODO: This in theory could error, but name should always be on json_schema
            # TODO: Make JSON schema a typed pydantic object
            self.name = self.json_schema.get("name")

        # Derive description from the JSON schema if not provided
        if not self.description:
            # TODO: This in theory could error, but description should always be on json_schema
            # TODO: Make JSON schema a typed pydantic object
            self.description = self.json_schema.get("description")

        return self


class ToolCreate(LettaBase):
    description: Optional[str] = Field(None, description="The description of the tool.")
    tags: List[str] = Field([], description="Metadata tags.")
    source_code: str = Field(..., description="The source code of the function.")
    source_type: str = Field("python", description="The source type of the function.")
    json_schema: Optional[Dict] = Field(
        None, description="The JSON schema of the function (auto-generated from source_code if not provided)"
    )
    args_json_schema: Optional[Dict] = Field(None, description="The args JSON schema of the function.")
    return_char_limit: int = Field(FUNCTION_RETURN_CHAR_LIMIT, description="The maximum number of characters in the response.")
    pip_requirements: list[PipRequirement] | None = Field(None, description="Optional list of pip packages required by this tool.")
    npm_requirements: list[NpmRequirement] | None = Field(None, description="Optional list of npm packages required by this tool.")

    @classmethod
    def from_mcp(cls, mcp_server_name: str, mcp_tool: MCPTool) -> "ToolCreate":
        from letta.functions.helpers import generate_mcp_tool_wrapper

        # Pass the MCP tool to the schema generator
        json_schema = generate_tool_schema_for_mcp(mcp_tool=mcp_tool)

        # Return a ToolCreate instance
        description = mcp_tool.description
        source_type = "python"
        tags = [f"{MCP_TOOL_TAG_NAME_PREFIX}:{mcp_server_name}"]
        wrapper_func_name, wrapper_function_str = generate_mcp_tool_wrapper(mcp_tool.name)

        return cls(
            description=description,
            source_type=source_type,
            tags=tags,
            source_code=wrapper_function_str,
            json_schema=json_schema,
        )

    @classmethod
    def from_composio(cls, action_name: str) -> "ToolCreate":
        """
        Class method to create an instance of Letta-compatible Composio Tool.
        Check https://docs.composio.dev/introduction/intro/overview to look at options for from_composio

        This function will error if we find more than one tool, or 0 tools.

        Args:
            action_name str: A action name to filter tools by.
        Returns:
            Tool: A Letta Tool initialized with attributes derived from the Composio tool.
        """
        from composio import ComposioToolSet, LogLevel

        composio_toolset = ComposioToolSet(logging_level=LogLevel.ERROR, lock=False)
        composio_action_schemas = composio_toolset.get_action_schemas(actions=[action_name], check_connected_accounts=False)

        assert len(composio_action_schemas) > 0, "User supplied parameters do not match any Composio tools"
        assert (
            len(composio_action_schemas) == 1
        ), f"User supplied parameters match too many Composio tools; {len(composio_action_schemas)} > 1"

        composio_action_schema = composio_action_schemas[0]

        description = composio_action_schema.description
        source_type = "python"
        tags = [COMPOSIO_TOOL_TAG_NAME]
        wrapper_func_name, wrapper_function_str = generate_composio_tool_wrapper(action_name)
        json_schema = generate_tool_schema_for_composio(composio_action_schema.parameters, name=wrapper_func_name, description=description)

        return cls(
            description=description,
            source_type=source_type,
            tags=tags,
            source_code=wrapper_function_str,
            json_schema=json_schema,
        )


class ToolUpdate(LettaBase):
    description: Optional[str] = Field(None, description="The description of the tool.")
    tags: Optional[List[str]] = Field(None, description="Metadata tags.")
    source_code: Optional[str] = Field(None, description="The source code of the function.")
    source_type: Optional[str] = Field(None, description="The type of the source code.")
    json_schema: Optional[Dict] = Field(
        None, description="The JSON schema of the function (auto-generated from source_code if not provided)"
    )
    args_json_schema: Optional[Dict] = Field(None, description="The args JSON schema of the function.")
    return_char_limit: Optional[int] = Field(None, description="The maximum number of characters in the response.")
    pip_requirements: list[PipRequirement] | None = Field(None, description="Optional list of pip packages required by this tool.")
    npm_requirements: list[NpmRequirement] | None = Field(None, description="Optional list of npm packages required by this tool.")

    class Config:
        extra = "ignore"  # Allows extra fields without validation errors
        # TODO: Remove this, and clean usage of ToolUpdate everywhere else


class ToolRunFromSource(LettaBase):
    source_code: str = Field(..., description="The source code of the function.")
    args: Dict[str, Any] = Field(..., description="The arguments to pass to the tool.")
    env_vars: Dict[str, str] = Field(None, description="The environment variables to pass to the tool.")
    name: Optional[str] = Field(None, description="The name of the tool to run.")
    source_type: Optional[str] = Field(None, description="The type of the source code.")
    args_json_schema: Optional[Dict] = Field(None, description="The args JSON schema of the function.")
    json_schema: Optional[Dict] = Field(
        None, description="The JSON schema of the function (auto-generated from source_code if not provided)"
    )
    pip_requirements: list[PipRequirement] | None = Field(None, description="Optional list of pip packages required by this tool.")
    npm_requirements: list[NpmRequirement] | None = Field(None, description="Optional list of npm packages required by this tool.")
