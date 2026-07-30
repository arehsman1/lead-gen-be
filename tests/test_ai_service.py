import pytest

from app.services.ai_service import AIServiceError, DEFAULT_MODEL, PROVIDER_MODELS, _NON_CHAT_MARKERS, _extract_json


def test_extract_json_plain():
    assert _extract_json('{"subject": "Hi", "body": "Hello"}') == {"subject": "Hi", "body": "Hello"}


def test_extract_json_strips_markdown_fences():
    # Claude/Gemini/Grok don't all support a strict JSON response mode the
    # way OpenAI's response_format does, so despite the prompt asking for
    # raw JSON, a model can still wrap its answer in code fences.
    text = '```json\n{"subject": "Hi", "body": "Hello"}\n```'
    assert _extract_json(text) == {"subject": "Hi", "body": "Hello"}


def test_extract_json_strips_bare_fences_no_language_tag():
    text = '```\n{"subject": "Hi", "body": "Hello"}\n```'
    assert _extract_json(text) == {"subject": "Hi", "body": "Hello"}


def test_extract_json_finds_object_amid_stray_text():
    text = 'Sure, here you go:\n{"subject": "Hi", "body": "Hello"}\nHope that helps!'
    assert _extract_json(text) == {"subject": "Hi", "body": "Hello"}


def test_extract_json_raises_on_garbage():
    with pytest.raises(AIServiceError):
        _extract_json("not json at all, sorry")


def test_every_provider_has_a_default_model():
    # DEFAULT_MODEL is used whenever Settings has a provider chosen but no
    # specific model saved yet — every provider PROVIDER_MODELS lists must
    # have a corresponding fallback, or that provider silently 404s.
    for provider in PROVIDER_MODELS:
        assert provider in DEFAULT_MODEL
        assert DEFAULT_MODEL[provider] in PROVIDER_MODELS[provider]


@pytest.mark.parametrize(
    "model_id",
    [
        "text-embedding-3-large",
        "whisper-1",
        "tts-1",
        "dall-e-3",
        "gpt-4o-realtime-preview",
        "gpt-4o-transcribe",
        "omni-moderation-latest",
    ],
)
def test_non_chat_markers_flag_non_chat_models(model_id):
    # OpenAI/Grok's /v1/models list mixes embeddings, audio, and image
    # models in with chat models, with no separate "type" field to filter
    # on — list_available_models relies on this heuristic to exclude them.
    assert any(marker in model_id.lower() for marker in _NON_CHAT_MARKERS)


@pytest.mark.parametrize("model_id", ["gpt-5.5", "gpt-4o", "gpt-4o-mini", "o1", "o3-mini"])
def test_non_chat_markers_do_not_flag_real_chat_models(model_id):
    assert not any(marker in model_id.lower() for marker in _NON_CHAT_MARKERS)
