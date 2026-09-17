from backend.app.consistency.character_dna import CharacterDNAManager


def test_character_dna_prompt_locking():
    char = CharacterDNAManager.create_character(
        character_id="char_elena",
        name="Elena",
        prompt_prefix="Elena, 28yo Asian female, navy blue tech hoodie, silver wireframe glasses, amber eyes",
        seed=2026
    )

    action_1 = "typing on a holographic laptop in a neon cyber cafe"
    prompt_1 = CharacterDNAManager.compose_consistent_prompt(char, action_1)

    action_2 = "looking directly at the camera with an amazed expression"
    prompt_2 = CharacterDNAManager.compose_consistent_prompt(char, action_2)

    # Invariant: Prompt prefix must start exactly identically
    assert prompt_1.startswith(char.prompt_prefix)
    assert prompt_2.startswith(char.prompt_prefix)
    assert action_1 in prompt_1
    assert action_2 in prompt_2
    assert len(char.reference_anchors) == 3
