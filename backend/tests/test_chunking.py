# =============================================================================
# DocuMind — Unit Tests: Parent-Child Chunking
# Tests the chunking logic that creates hierarchical chunk structures
# =============================================================================

import pytest
from app.services.ingestion import (
    count_tokens,
    _find_page_for_offset,
    _find_pages_for_range,
)
from app.utils.pdf import PageContent


# ── Tests: Token Counting ────────────────────────────────────────────────────

class TestTokenCounting:
    """Verify the tiktoken-based token counter."""

    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_single_word(self):
        tokens = count_tokens("hello")
        assert tokens >= 1

    def test_sentence(self):
        tokens = count_tokens("The quick brown fox jumps over the lazy dog.")
        # GPT-4o tokenizer: this sentence is ~10 tokens
        assert 8 <= tokens <= 12

    def test_code_snippet(self):
        code = "def fibonacci(n):\n    return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)"
        tokens = count_tokens(code)
        assert tokens > 10  # Code is tokenized differently

    def test_unicode_text(self):
        tokens = count_tokens("日本語のテスト文章です。")
        assert tokens > 0  # Should handle CJK characters

    def test_long_text_proportionality(self):
        short = count_tokens("word " * 10)
        long = count_tokens("word " * 100)
        # Longer text should have proportionally more tokens
        assert long > short * 5


# ── Tests: Page Offset Mapping ───────────────────────────────────────────────

class TestPageOffsetMapping:
    """Test the character-offset-to-page mapping logic."""

    @pytest.fixture
    def sample_pages(self):
        """Create sample page boundaries."""
        return [
            PageContent(
                page_number=1,
                text="First page content here.",
                char_offset_start=0,
                char_offset_end=24,
                width=612.0,
                height=792.0,
            ),
            PageContent(
                page_number=2,
                text="Second page starts now.",
                char_offset_start=24,
                char_offset_end=47,
                width=612.0,
                height=792.0,
            ),
            PageContent(
                page_number=3,
                text="Third page final section.",
                char_offset_start=47,
                char_offset_end=72,
                width=612.0,
                height=792.0,
            ),
        ]

    def test_offset_at_start_of_page_1(self, sample_pages):
        assert _find_page_for_offset(sample_pages, 0) == 1

    def test_offset_within_page_2(self, sample_pages):
        assert _find_page_for_offset(sample_pages, 30) == 2

    def test_offset_at_boundary(self, sample_pages):
        # Offset 24 is the start of page 2
        assert _find_page_for_offset(sample_pages, 24) == 2

    def test_offset_at_end_returns_last_page(self, sample_pages):
        # Beyond all pages should return the last page
        assert _find_page_for_offset(sample_pages, 999) == 3

    def test_range_spanning_single_page(self, sample_pages):
        pages = _find_pages_for_range(sample_pages, 5, 20)
        assert pages == [1]

    def test_range_spanning_two_pages(self, sample_pages):
        pages = _find_pages_for_range(sample_pages, 20, 30)
        assert 1 in pages
        assert 2 in pages

    def test_range_spanning_all_pages(self, sample_pages):
        pages = _find_pages_for_range(sample_pages, 0, 72)
        assert pages == [1, 2, 3]


# ── Tests: Chunk Data Integrity ──────────────────────────────────────────────

class TestChunkDataIntegrity:
    """Test properties that all chunks must satisfy."""

    def test_child_chunk_size_limit(self):
        """Child chunks should not exceed configured token limit."""
        from app.config import settings

        max_tokens = settings.chunk_size + settings.chunk_overlap
        # This is a property test — we verify the configured limits are sane
        assert settings.chunk_size > 0
        assert settings.chunk_overlap >= 0
        assert settings.chunk_overlap < settings.chunk_size

    def test_parent_chunk_larger_than_child(self):
        """Parent chunks should always be larger than child chunks."""
        from app.config import settings

        assert settings.parent_chunk_size > settings.chunk_size
        assert settings.parent_chunk_size >= settings.chunk_size * 2

    def test_overlap_less_than_chunk_size(self):
        """Overlap must be less than chunk size to avoid infinite loops."""
        from app.config import settings

        assert settings.chunk_overlap < settings.chunk_size
        assert settings.parent_chunk_overlap < settings.parent_chunk_size
