#!/usr/bin/env python3
"""
RPA Complexity Assessment Agent — Phase 2 Validation Script

This is the phase gate for Phase 2 (LLM Abstraction Layer). It validates
the entire LLM layer end-to-end, including:
- Settings and configuration loading
- Provider interface implementation
- Retry logic with exponential backoff
- Live API calls to verify the configured provider works

Run with: uv run python scripts/validate_llm_layer.py
Exit code: 0 if all validations pass, 1 if any fail.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path so imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.logging_config import setup_logging
from config.settings import get_settings
from core.exceptions import LLMProviderError
from llm.manager import LLMManager
from llm.providers import BaseLLMProvider, LLMResponse
from llm.providers.anthropic_provider import AnthropicProvider
from llm.providers.ollama_provider import OllamaProvider
from llm.providers.openai_provider import OpenAIProvider
from llm.providers.watsonx_provider import WatsonxProvider
from pydantic import BaseModel


def print_header():
    """Print the validation script header."""
    print("═" * 67)
    print("  RPA Complexity Assessment Agent — LLM Layer Validation")
    print("  Phase 2 Gate Check")
    print("═" * 67)
    print()


def print_section(title: str):
    """Print a section header."""
    print(f"{title}")


def print_result(case_id: str, passed: bool, description: str, details: str = ""):
    """Print a single validation result."""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {case_id}: {description}", end="")
    if details:
        print(f" ({details})", end="")
    print()


def print_footer(total_cases: int, passed_cases: int):
    """Print the validation footer."""
    print()
    print("─" * 67)
    print(f"  Results: {passed_cases}/{total_cases} cases passed")

    if passed_cases == total_cases:
        print("  Status:  ✅ PHASE 2 GATE — PASSED")
        print("  LLM abstraction layer is validated.")
        print("  Safe to proceed to Phase 3.")
    else:
        failed = total_cases - passed_cases
        print(f"  Status:  ❌ PHASE 2 GATE — FAILED ({failed} case(s) failed)")
        print("  Fix all failures before proceeding to Phase 3.")

    print("═" * 67)


def validate_section_a():
    """Validate settings and configuration."""
    results = []

    print_section("SECTION A — Settings & Configuration")

    # A1: Settings loads without error
    try:
        settings = get_settings()
        a1_pass = (
            isinstance(settings.default_llm_provider, str)
            and len(settings.default_llm_provider) > 0
            and isinstance(settings.default_llm_model, str)
            and len(settings.default_llm_model) > 0
            and settings.llm_max_retries >= 1
        )
        print_result("A1", a1_pass, "Settings loads without error")
    except Exception as e:
        print_result("A1", False, "Settings loads without error", f"exception: {e}")
        a1_pass = False

    results.append(a1_pass)

    # A2: Settings reflects .env values
    try:
        provider = settings.default_llm_provider.lower()
        api_key = ""
        if provider == "anthropic":
            api_key = settings.anthropic_api_key
        elif provider == "openai":
            api_key = settings.openai_api_key

        a2_pass = (
            provider == settings.default_llm_provider.lower()
            and (api_key.startswith("sk-") or provider in ["ollama", "watsonx"])
        )
        print_result(
            "A2",
            a2_pass,
            f"Settings reflects .env (provider={provider})",
            "key present" if a2_pass else "key missing",
        )
    except Exception as e:
        print_result("A2", False, "Settings reflects .env", f"exception: {e}")
        a2_pass = False

    results.append(a2_pass)

    # A3: LLMManager builds without error
    try:
        manager = LLMManager()
        info = manager.get_provider_info()
        a3_pass = (
            "provider" in info
            and "model" in info
            and info["call_count"] == "0"
        )
        print_result("A3", a3_pass, "LLMManager builds without error", "call_count=0")
    except Exception as e:
        print_result("A3", False, "LLMManager builds without error", f"exception: {e}")
        a3_pass = False

    results.append(a3_pass)

    return results


def validate_section_b():
    """Validate provider interface implementation."""
    results = []

    print()
    print_section("SECTION B — Provider Interface")

    # B1: All providers import and implement interface
    b1_pass = True
    providers_to_test = [
        ("AnthropicProvider", AnthropicProvider),
        ("OpenAIProvider", OpenAIProvider),
        ("OllamaProvider", OllamaProvider),
        ("WatsonxProvider", WatsonxProvider),
    ]

    for name, provider_class in providers_to_test:
        if not issubclass(provider_class, BaseLLMProvider):
            b1_pass = False

    # Test that WatsonxProvider raises NotImplementedError
    try:
        watsonx = WatsonxProvider("key", "url", "project")
        watsonx.complete("prompt")
        b1_pass = False
    except NotImplementedError:
        pass
    except Exception:
        b1_pass = False

    print_result("B1", b1_pass, "All 4 providers import and subclass BaseLLMProvider")
    results.append(b1_pass)

    # B2: LLMResponse total_tokens calculation
    try:
        response = LLMResponse(
            content="test",
            model="test",
            provider="test",
            input_tokens=75,
            output_tokens=75,
            raw_response={},
        )
        b2_pass = response.total_tokens == 150
        print_result(
            "B2",
            b2_pass,
            "LLMResponse.total_tokens()",
            f"150 == {response.total_tokens}",
        )
    except Exception as e:
        print_result("B2", False, "LLMResponse.total_tokens()", str(e))
        b2_pass = False

    results.append(b2_pass)

    # B3: build_json_system_prompt
    try:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            from config.settings import get_settings
            get_settings.cache_clear()

            provider = AnthropicProvider(api_key="sk-ant-test", model="claude")

            class TestSchema(BaseModel):
                field1: str
                field2: int

            result = provider.build_json_system_prompt(
                "base prompt", TestSchema
            )
            b3_pass = (
                "Respond with valid JSON only" in result
                and "field1" in result
                and "field2" in result
            )
            print_result(
                "B3",
                b3_pass,
                "build_json_system_prompt includes JSON instructions",
                "instructions present" if b3_pass else "missing",
            )
    except Exception as e:
        print_result("B3", False, "build_json_system_prompt", str(e))
        b3_pass = False

    results.append(b3_pass)

    # B4: parse_json_response error handling
    b4_pass = True
    b4_checks = 0

    try:
        provider = AnthropicProvider(api_key="sk-ant-test", model="claude")

        class StatusSchema(BaseModel):
            status: str

        # Valid JSON
        try:
            result = provider.parse_json_response('{"status": "ok"}', StatusSchema)
            if isinstance(result, StatusSchema) and result.status == "ok":
                b4_checks += 1
        except Exception:
            b4_pass = False

        # Invalid JSON
        try:
            provider.parse_json_response("not json", StatusSchema)
            b4_pass = False
        except LLMProviderError:
            b4_checks += 1
        except Exception:
            b4_pass = False

        # Mismatched schema
        try:
            provider.parse_json_response(
                '{"wrong_field": "value"}', StatusSchema
            )
            b4_pass = False
        except LLMProviderError:
            b4_checks += 1
        except Exception:
            b4_pass = False

        b4_pass = b4_pass and b4_checks == 3
        print_result(
            "B4",
            b4_pass,
            "parse_json_response handles valid/invalid/mismatch",
            f"{b4_checks}/3 correct",
        )
    except Exception as e:
        print_result("B4", False, "parse_json_response", str(e))
        b4_pass = False

    results.append(b4_pass)

    return results


def validate_section_c():
    """Validate retry logic with mocking."""
    results = []

    print()
    print_section("SECTION C — Retry Logic (mocked)")

    # C1: Retry on rate limit
    try:
        with patch("llm.manager.get_settings") as mock_settings, patch(
            "llm.manager.AnthropicProvider"
        ) as mock_provider_class:

            mock_settings_obj = MagicMock()
            mock_settings_obj.default_llm_provider = "anthropic"
            mock_settings_obj.default_llm_model = "claude"
            mock_settings_obj.anthropic_api_key = "sk-test"
            mock_settings_obj.llm_max_retries = 3
            mock_settings_obj.llm_retry_base_delay = 0.01
            mock_settings.return_value = mock_settings_obj

            mock_response = LLMResponse(
                content="success",
                model="claude",
                provider="anthropic",
                input_tokens=10,
                output_tokens=20,
                raw_response={},
            )

            mock_provider = MagicMock()
            mock_provider.complete.side_effect = [
                LLMProviderError("rate limit exceeded"),
                LLMProviderError("429 too many requests"),
                mock_response,
            ]
            mock_provider_class.return_value = mock_provider

            manager = LLMManager()

            with patch("time.sleep"):
                result = manager.complete("test")

            c1_pass = (
                result == "success" and mock_provider.complete.call_count == 3
            )
            print_result(
                "C1",
                c1_pass,
                "Retries on rate limit",
                f"{mock_provider.complete.call_count} calls",
            )
    except Exception as e:
        print_result("C1", False, "Retries on rate limit", str(e))
        c1_pass = False

    results.append(c1_pass)

    # C2: No retry on auth error
    try:
        with patch("llm.manager.get_settings") as mock_settings, patch(
            "llm.manager.AnthropicProvider"
        ) as mock_provider_class:

            mock_settings_obj = MagicMock()
            mock_settings_obj.default_llm_provider = "anthropic"
            mock_settings_obj.default_llm_model = "claude"
            mock_settings_obj.anthropic_api_key = "sk-test"
            mock_settings_obj.llm_max_retries = 3
            mock_settings_obj.llm_retry_base_delay = 1.0
            mock_settings.return_value = mock_settings_obj

            mock_provider = MagicMock()
            mock_provider.complete.side_effect = LLMProviderError(
                "authentication failed"
            )
            mock_provider_class.return_value = mock_provider

            manager = LLMManager()

            try:
                manager.complete("test")
                c2_pass = False
            except LLMProviderError:
                c2_pass = mock_provider.complete.call_count == 1

            print_result(
                "C2",
                c2_pass,
                "No retry on auth error",
                f"{mock_provider.complete.call_count} calls",
            )
    except Exception as e:
        print_result("C2", False, "No retry on auth error", str(e))
        c2_pass = False

    results.append(c2_pass)

    # C3: Raise after retry exhaustion
    try:
        with patch("llm.manager.get_settings") as mock_settings, patch(
            "llm.manager.AnthropicProvider"
        ) as mock_provider_class:

            mock_settings_obj = MagicMock()
            mock_settings_obj.default_llm_provider = "anthropic"
            mock_settings_obj.default_llm_model = "claude"
            mock_settings_obj.anthropic_api_key = "sk-test"
            mock_settings_obj.llm_max_retries = 3
            mock_settings_obj.llm_retry_base_delay = 0.01
            mock_settings.return_value = mock_settings_obj

            mock_provider = MagicMock()
            mock_provider.complete.side_effect = LLMProviderError(
                "rate limit exceeded"
            )
            mock_provider_class.return_value = mock_provider

            manager = LLMManager()

            try:
                with patch("time.sleep"):
                    manager.complete("test")
                c3_pass = False
            except LLMProviderError:
                c3_pass = mock_provider.complete.call_count == 3

            print_result(
                "C3",
                c3_pass,
                "Raises after retry exhaustion",
                f"{mock_provider.complete.call_count} calls",
            )
    except Exception as e:
        print_result("C3", False, "Raises after retry exhaustion", str(e))
        c3_pass = False

    results.append(c3_pass)

    return results


def validate_section_d():
    """Validate with live API calls."""
    results = []

    print()
    print_section("SECTION D — Live API Validation")

    # Setup logging for live calls
    setup_logging("DEBUG")

    # D1: Real completion call
    try:
        manager = LLMManager()
        result = manager.complete(
            prompt="Reply with exactly these words: VALIDATION OK",
            system="You are a test assistant. Follow instructions exactly.",
            max_tokens=20,
            session_id="validate_llm_layer",
        )
        
        result_upper = result.upper()
        d1_pass = (
            isinstance(result, str)
            and len(result) > 0
            and ("VALIDATION" in result_upper or "OK" in result_upper)
        )
        
        print_result("D1", d1_pass, "Real completion call", f"response OK")
        if d1_pass:
            print(f"    Actual response: {result[:100]}")

    except Exception as e:
        print_result("D1", False, "Real completion call", f"exception: {e}")
        d1_pass = False

    results.append(d1_pass)

    # D2: Provider info after live call
    try:
        info = manager.get_provider_info()
        d2_pass = (
            int(info["call_count"]) >= 1
            and int(info["total_tokens"]) > 0
        )
        print_result("D2", d2_pass, "Provider info after live call")
        if d2_pass:
            print(f"    Info: {info}")

    except Exception as e:
        print_result("D2", False, "Provider info after live call", str(e))
        d2_pass = False

    results.append(d2_pass)

    # D3: Structured completion call
    try:
        class StatusResponse(BaseModel):
            status: str
            message: str

        manager = LLMManager()
        result = manager.complete_structured(
            prompt="Return a JSON with status='ok' and message='ready'",
            response_schema=StatusResponse,
            max_tokens=50,
            session_id="validate_llm_layer_structured",
        )

        d3_pass = (
            isinstance(result, StatusResponse)
            and result.status is not None
            and len(result.status) > 0
        )
        print_result("D3", d3_pass, "Structured completion call")
        if d3_pass:
            print(f"    Result: status={result.status}, message={result.message}")

    except Exception as e:
        print_result("D3", False, "Structured completion call", f"exception: {e}")
        d3_pass = False

    results.append(d3_pass)

    return results


def main():
    """Run all validation cases and report results."""
    print_header()

    try:
        section_a = validate_section_a()
        section_b = validate_section_b()
        section_c = validate_section_c()
        section_d = validate_section_d()

        all_results = section_a + section_b + section_c + section_d
        total_cases = len(all_results)
        passed_cases = sum(1 for r in all_results if r)

        print_footer(total_cases, passed_cases)

        if passed_cases == total_cases:
            return 0
        else:
            return 1

    except Exception as e:
        print()
        print(f"[ERROR] Validation failed with exception: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
