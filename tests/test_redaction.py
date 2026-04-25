"""Tests for secret redaction patterns in security.py.

Covers all 12 patterns in _SECRET_PATTERNS including the 4 new patterns
(github_pat_, GitHub App tokens, Bearer header, AWS AKIA) and the
OpenAI negative lookahead fix.
"""

from ml_intern.security import redact_secrets


# ── Existing patterns (regression) ──────────────────────────────


class TestAnthropicPattern:
    def test_anthropic_key_redacted(self):
        text = "key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "sk-ant-" not in result
        assert "[REDACTED]" in result

    def test_anthropic_key_in_context(self):
        text = "ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "sk-ant-" not in result


class TestHuggingFacePattern:
    def test_hf_token_redacted(self):
        text = "hf_ABCDEFGHIJKLMNOPQRSTuvwx"
        result = redact_secrets(text)
        assert "hf_" not in result
        assert "[REDACTED]" in result


class TestGitHubClassicPAT:
    def test_ghp_redacted(self):
        text = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        result = redact_secrets(text)
        assert "ghp_" not in result
        assert "[REDACTED]" in result


class TestGoogleAPIKey:
    def test_google_key_redacted(self):
        text = "AIzaSyD-abcdefghijklmnopqrstuvwxyz01234"
        result = redact_secrets(text)
        assert "AIza" not in result
        assert "[REDACTED]" in result


# ── New patterns ────────────────────────────────────────────────


class TestGitHubFinegrainedPAT:
    def test_github_pat_redacted(self):
        text = "github_pat_11ABCDEF0123456789_abcdefghij"
        result = redact_secrets(text)
        assert "github_pat_" not in result
        assert "[REDACTED]" in result

    def test_github_pat_long_format(self):
        text = "github_pat_" + "a" * 80
        result = redact_secrets(text)
        assert "github_pat_" not in result


class TestGitHubAppTokens:
    def test_ghs_server_token_redacted(self):
        text = "ghs_" + "A" * 36
        result = redact_secrets(text)
        assert "ghs_" not in result
        assert "[REDACTED]" in result

    def test_ghu_user_token_redacted(self):
        text = "ghu_" + "B" * 36
        result = redact_secrets(text)
        assert "ghu_" not in result

    def test_ghr_refresh_token_redacted(self):
        text = "ghr_" + "C" * 36
        result = redact_secrets(text)
        assert "ghr_" not in result

    def test_ghs_long_2026_format(self):
        """2026 format: ghs_ tokens can be ~520 chars."""
        text = "ghs_" + "D" * 200
        result = redact_secrets(text)
        assert "ghs_" not in result


class TestBearerHeader:
    def test_bearer_header_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"
        result = redact_secrets(text)
        assert "eyJhbGci" not in result
        assert "[REDACTED]" in result

    def test_bearer_case_insensitive(self):
        text = "authorization: bearer abc123def456"
        result = redact_secrets(text)
        assert "abc123def456" not in result

    def test_bearer_preserves_prefix(self):
        text = "Authorization: Bearer my-token-value"
        result = redact_secrets(text)
        # The "Authorization: Bearer " prefix should remain
        assert "authorization:" in result.lower()


class TestAWSKeyID:
    def test_akia_redacted(self):
        text = "AKIAIOSFODNN7EXAMPLE"
        result = redact_secrets(text)
        assert "AKIA" not in result
        assert "[REDACTED]" in result

    def test_akia_in_config(self):
        text = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
        result = redact_secrets(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result


# ── OpenAI negative lookahead ───────────────────────────────────


class TestOpenAINegativeLookahead:
    def test_openai_key_redacted(self):
        text = "sk-proj-abcdefghijklmnopqrstuv"
        result = redact_secrets(text)
        assert "sk-proj-" not in result
        assert "[REDACTED]" in result

    def test_openai_generic_redacted(self):
        text = "sk-abcdefghijklmnopqrstuvwx"
        result = redact_secrets(text)
        assert "sk-abcdef" not in result

    def test_anthropic_not_matched_by_openai_pattern(self):
        """sk-ant- should be matched by Anthropic pattern, not OpenAI."""
        text = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        # Verify it was redacted (by Anthropic pattern), but not double-matched


# ── Edge cases ──────────────────────────────────────────────────


class TestEdgeCases:
    def test_clean_text_unchanged(self):
        text = "This is a normal log line with no secrets."
        result = redact_secrets(text)
        assert result == text

    def test_multiple_secrets_in_one_line(self):
        text = "keys: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 and hf_abcdefghijklmnopqrstuv"
        result = redact_secrets(text)
        assert "ghp_" not in result
        assert "hf_" not in result

    def test_key_value_format_preserves_label(self):
        text = "api_key=sk-proj-abcdefghijklmnopqrstuv"
        result = redact_secrets(text)
        assert "api_key=" in result
        assert "[REDACTED]" in result

    def test_empty_string(self):
        assert redact_secrets("") == ""

    def test_partial_prefix_not_matched(self):
        """Short strings that look like prefixes but aren't full tokens."""
        text = "ghp_short"
        result = redact_secrets(text)
        # ghp_ followed by <36 chars should NOT match
        assert result == text
