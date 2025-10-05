import pytest

from nexus.agents.memnon.utils.search import SearchManager


class DummyEmbeddingManager:
    def get_available_models(self):
        return []

    def generate_embedding(self, query_text, model_key):
        raise NotImplementedError


class DummyIDFDictionary:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_idf(self, term: str) -> float:
        return self.mapping.get(term, 1.0)


@pytest.fixture
def base_settings():
    return {
        "retrieval": {
            "hybrid_search": {
                "enabled": True,
                "vector_weight_default": 0.6,
                "text_weight_default": 0.4,
                "rare_term_min_text_weight": 0.5,
            }
        }
    }


@pytest.fixture
def retrieval_settings():
    return {
        "default_top_k": 10,
        "model_weights": {},
    }


def make_manager(idf_mapping, settings, retrieval_settings):
    return SearchManager(
        db_url="postgresql://user:pass@localhost/db",
        embedding_manager=DummyEmbeddingManager(),
        idf_dictionary=DummyIDFDictionary(idf_mapping),
        settings=settings,
        retrieval_settings=retrieval_settings,
    )


def test_rare_term_boosts_text_weight(base_settings, retrieval_settings):
    manager = make_manager({"resurrection": 3.2}, base_settings, retrieval_settings)

    vector_weight, text_weight = manager._adjust_weights_for_rare_terms(
        query_text="resurrection encounter",
        vector_weight=0.8,
        text_weight=0.2,
        query_type="character",
    )

    assert pytest.approx(text_weight) == 0.5
    assert pytest.approx(vector_weight) == 0.5


def test_non_rare_query_leaves_weights_unchanged(base_settings, retrieval_settings):
    manager = make_manager({}, base_settings, retrieval_settings)

    vector_weight, text_weight = manager._adjust_weights_for_rare_terms(
        query_text="common words only",
        vector_weight=0.7,
        text_weight=0.3,
        query_type="general",
    )

    assert pytest.approx(text_weight) == 0.3
    assert pytest.approx(vector_weight) == 0.7


def test_excluded_query_type_skips_boost(base_settings, retrieval_settings):
    settings = {
        "retrieval": {
            "hybrid_search": {
                "enabled": True,
                "vector_weight_default": 0.6,
                "text_weight_default": 0.4,
                "rare_term_min_text_weight": 0.5,
                "rare_term_excluded_query_types": ["lore"],
            }
        }
    }
    manager = make_manager({"resurrection": 3.2}, settings, retrieval_settings)

    vector_weight, text_weight = manager._adjust_weights_for_rare_terms(
        query_text="resurrection encounter",
        vector_weight=0.8,
        text_weight=0.2,
        query_type="lore",
    )

    assert pytest.approx(text_weight) == 0.2
    assert pytest.approx(vector_weight) == 0.8
