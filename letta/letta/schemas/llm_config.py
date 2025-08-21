from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from letta.constants import LETTA_MODEL_ENDPOINT
from letta.log import get_logger
from letta.schemas.enums import ProviderCategory

logger = get_logger(__name__)


class LLMConfig(BaseModel):
    """Configuration for Language Model (LLM) connection and generation parameters."""

    model: str = Field(..., description="LLM model name. ")
    model_endpoint_type: Literal[
        "openai",
        "anthropic",
        "cohere",
        "google_ai",
        "google_vertex",
        "azure",
        "groq",
        "ollama",
        "webui",
        "webui-legacy",
        "lmstudio",
        "lmstudio-legacy",
        "lmstudio-chatcompletions",
        "llamacpp",
        "koboldcpp",
        "vllm",
        "hugging-face",
        "mistral",
        "together",  # completions endpoint
        "bedrock",
        "deepseek",
        "xai",
    ] = Field(..., description="The endpoint type for the model.")
    model_endpoint: Optional[str] = Field(None, description="The endpoint for the model.")
    provider_name: Optional[str] = Field(None, description="The provider name for the model.")
    provider_category: Optional[ProviderCategory] = Field(None, description="The provider category for the model.")
    model_wrapper: Optional[str] = Field(None, description="The wrapper for the model.")
    context_window: int = Field(..., description="The context window size for the model.")
    put_inner_thoughts_in_kwargs: Optional[bool] = Field(
        True,
        description="Puts 'inner_thoughts' as a kwarg in the function call if this is set to True. This helps with function calling performance and also the generation of inner thoughts.",
    )
    handle: Optional[str] = Field(None, description="The handle for this config, in the format provider/model-name.")
    temperature: float = Field(
        0.7,
        description="The temperature to use when generating text with the model. A higher temperature will result in more random text.",
    )
    max_tokens: Optional[int] = Field(
        4096,
        description="The maximum number of tokens to generate. If not set, the model will use its default value.",
    )
    enable_reasoner: bool = Field(
        False, description="Whether or not the model should use extended thinking if it is a 'reasoning' style model"
    )
    reasoning_effort: Optional[Literal["minimal", "low", "medium", "high"]] = Field(
        None,
        description="The reasoning effort to use when generating text reasoning models",
    )
    max_reasoning_tokens: int = Field(
        0,
        description="Configurable thinking budget for extended thinking. Used for enable_reasoner and also for Google Vertex models like Gemini 2.5 Flash. Minimum value is 1024 when used with enable_reasoner.",
    )
    frequency_penalty: Optional[float] = Field(
        None,  # Can also deafult to 0.0?
        description="Positive values penalize new tokens based on their existing frequency in the text so far, decreasing the model's likelihood to repeat the same line verbatim. From OpenAI: Number between -2.0 and 2.0.",
    )
    compatibility_type: Optional[Literal["gguf", "mlx"]] = Field(None, description="The framework compatibility type for the model.")

    # FIXME hack to silence pydantic protected namespace warning
    model_config = ConfigDict(protected_namespaces=())

    @model_validator(mode="before")
    @classmethod
    def set_default_enable_reasoner(cls, values):
        # NOTE: this is really only applicable for models that can toggle reasoning on-and-off, like 3.7
        # We can also use this field to identify if a model is a "reasoning" model (o1/o3, etc.) if we want
        # if any(openai_reasoner_model in values.get("model", "") for openai_reasoner_model in ["o3-mini", "o1"]):
        #     values["enable_reasoner"] = True
        #     values["put_inner_thoughts_in_kwargs"] = False
        return values

    @model_validator(mode="before")
    @classmethod
    def set_default_put_inner_thoughts(cls, values):
        """
        Dynamically set the default for put_inner_thoughts_in_kwargs based on the model field,
        falling back to True if no specific rule is defined.
        """
        model = values.get("model")

        if model is None:
            return values

        # Define models where we want put_inner_thoughts_in_kwargs to be False
        avoid_put_inner_thoughts_in_kwargs = ["gpt-4"]

        if values.get("put_inner_thoughts_in_kwargs") is None:
            values["put_inner_thoughts_in_kwargs"] = False if model in avoid_put_inner_thoughts_in_kwargs else True

        # For the o1/o3 series from OpenAI, set to False by default
        # We can set this flag to `true` if desired, which will enable "double-think"
        from letta.llm_api.openai_client import is_openai_reasoning_model

        if is_openai_reasoning_model(model):
            values["put_inner_thoughts_in_kwargs"] = False

        if values.get("model_endpoint_type") == "anthropic" and (
            model.startswith("claude-3-7-sonnet") or model.startswith("claude-sonnet-4") or model.startswith("claude-opus-4")
        ):
            values["put_inner_thoughts_in_kwargs"] = False

        return values

    @classmethod
    def default_config(cls, model_name: str):
        """
        Convenience function to generate a default `LLMConfig` from a model name. Only some models are supported in this function.

        Args:
            model_name (str): The name of the model (gpt-4, gpt-4o-mini, letta).
        """
        if model_name == "gpt-4":
            return cls(
                model="gpt-4",
                model_endpoint_type="openai",
                model_endpoint="https://api.openai.com/v1",
                model_wrapper=None,
                context_window=8192,
                put_inner_thoughts_in_kwargs=True,
            )
        elif model_name == "gpt-4o-mini":
            return cls(
                model="gpt-4o-mini",
                model_endpoint_type="openai",
                model_endpoint="https://api.openai.com/v1",
                model_wrapper=None,
                context_window=128000,
            )
        elif model_name == "gpt-4o":
            return cls(
                model="gpt-4o",
                model_endpoint_type="openai",
                model_endpoint="https://api.openai.com/v1",
                model_wrapper=None,
                context_window=128000,
            )
        elif model_name == "gpt-4.1":
            return cls(
                model="gpt-4.1",
                model_endpoint_type="openai",
                model_endpoint="https://api.openai.com/v1",
                model_wrapper=None,
                context_window=256000,
                max_tokens=8192,
            )
        elif model_name == "letta":
            return cls(
                model="memgpt-openai",
                model_endpoint_type="openai",
                model_endpoint=LETTA_MODEL_ENDPOINT,
                context_window=30000,
            )
        else:
            raise ValueError(f"Model {model_name} not supported.")

    def pretty_print(self) -> str:
        return (
            f"{self.model}"
            + (f" [type={self.model_endpoint_type}]" if self.model_endpoint_type else "")
            + (f" [ip={self.model_endpoint}]" if self.model_endpoint else "")
        )

    @classmethod
    def is_openai_reasoning_model(cls, config: "LLMConfig") -> bool:
        return config.model_endpoint_type == "openai" and (
            config.model.startswith("o1") or config.model.startswith("o3") or config.model.startswith("o4")
        )

    @classmethod
    def is_anthropic_reasoning_model(cls, config: "LLMConfig") -> bool:
        return config.model_endpoint_type == "anthropic" and (
            config.model.startswith("claude-opus-4")
            or config.model.startswith("claude-sonnet-4")
            or config.model.startswith("claude-3-7-sonnet")
        )

    @classmethod
    def is_google_vertex_reasoning_model(cls, config: "LLMConfig") -> bool:
        return config.model_endpoint_type == "google_vertex" and (
            config.model.startswith("gemini-2.5-flash") or config.model.startswith("gemini-2.5-pro")
        )

    @classmethod
    def apply_reasoning_setting_to_config(cls, config: "LLMConfig", reasoning: bool):
        if not reasoning:
            if cls.is_openai_reasoning_model(config) or config.model.startswith("gemini-2.5-pro"):
                raise ValueError("Reasoning cannot be disabled for OpenAI o1/o3 models")
            config.put_inner_thoughts_in_kwargs = False
            config.enable_reasoner = False

        else:
            config.enable_reasoner = True
            if cls.is_anthropic_reasoning_model(config):
                config.put_inner_thoughts_in_kwargs = False
                if config.max_reasoning_tokens == 0:
                    config.max_reasoning_tokens = 1024
            elif cls.is_google_vertex_reasoning_model(config):
                # Handle as non-reasoner until we support summary
                config.put_inner_thoughts_in_kwargs = True
                if config.max_reasoning_tokens == 0:
                    config.max_reasoning_tokens = 1024
            elif cls.is_openai_reasoning_model(config):
                config.put_inner_thoughts_in_kwargs = False
                if config.reasoning_effort is None:
                    config.reasoning_effort = "medium"
            else:
                config.put_inner_thoughts_in_kwargs = True

        return config
