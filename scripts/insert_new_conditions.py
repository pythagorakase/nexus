#!/usr/bin/env python3
"""Insert new Kimi K2 and Hermes 4 condition records."""

from nexus.audition import AuditionEngine
from nexus.audition.models import ConditionSpec

def main():
    engine = AuditionEngine()

    # Kimi K2 conditions
    kimi_conditions = [
        ConditionSpec(
            slug="kimi-k2-t060",
            provider="openrouter",
            model="kimi-k2-0905-preview",
            label="Kimi K2 T=0.60",
            temperature=0.60,
            is_active=True,
            is_visible=True,
        ),
        ConditionSpec(
            slug="kimi-k2-t075-tp095-fp02",
            provider="openrouter",
            model="kimi-k2-0905-preview",
            label="Kimi K2 T=0.75 TP=0.95 FP=0.2",
            temperature=0.75,
            top_p=0.95,
            frequency_penalty=0.2,
            is_active=True,
            is_visible=True,
        ),
        ConditionSpec(
            slug="kimi-k2-t080-tp095-fp03",
            provider="openrouter",
            model="kimi-k2-0905-preview",
            label="Kimi K2 T=0.80 TP=0.95 FP=0.3",
            temperature=0.80,
            top_p=0.95,
            frequency_penalty=0.3,
            is_active=True,
            is_visible=True,
        ),
        ConditionSpec(
            slug="kimi-k2-t090-tp090-fp05-pp03-rp11",
            provider="openrouter",
            model="kimi-k2-0905-preview",
            label="Kimi K2 T=0.90 TP=0.90 FP=0.5 PP=0.3 RP=1.1",
            temperature=0.90,
            top_p=0.90,
            frequency_penalty=0.5,
            presence_penalty=0.3,
            repetition_penalty=1.1,
            is_active=True,
            is_visible=True,
        ),
    ]

    # Hermes 4 conditions
    hermes_conditions = [
        ConditionSpec(
            slug="hermes4-t09-minp005-rp110",
            provider="openrouter",
            model="Hermes-4-405B",
            label="Hermes 4 T=0.9 MinP=0.05 RP=1.10",
            temperature=0.9,
            min_p=0.05,
            repetition_penalty=1.10,
            is_active=True,
            is_visible=True,
        ),
        ConditionSpec(
            slug="hermes4-t11-minp008-tp092-rp115",
            provider="openrouter",
            model="Hermes-4-405B",
            label="Hermes 4 T=1.1 MinP=0.08 TP=0.92 RP=1.15",
            temperature=1.1,
            min_p=0.08,
            top_p=0.92,
            repetition_penalty=1.15,
            is_active=True,
            is_visible=True,
        ),
        ConditionSpec(
            slug="hermes4-t13-minp010-tp088-rp120",
            provider="openrouter",
            model="Hermes-4-405B",
            label="Hermes 4 T=1.3 MinP=0.10 TP=0.88 RP=1.20",
            temperature=1.3,
            min_p=0.10,
            top_p=0.88,
            repetition_penalty=1.20,
            is_active=True,
            is_visible=True,
        ),
        ConditionSpec(
            slug="hermes4-t15-minp012-tp085-rp125-pp02",
            provider="openrouter",
            model="Hermes-4-405B",
            label="Hermes 4 T=1.5 MinP=0.12 TP=0.85 RP=1.25 PP=0.2",
            temperature=1.5,
            min_p=0.12,
            top_p=0.85,
            repetition_penalty=1.25,
            presence_penalty=0.2,
            is_active=True,
            is_visible=True,
        ),
        ConditionSpec(
            slug="hermes4-t17-minp015-tp082-rp130-pp03",
            provider="openrouter",
            model="Hermes-4-405B",
            label="Hermes 4 T=1.7 MinP=0.15 TP=0.82 RP=1.30 PP=0.3",
            temperature=1.7,
            min_p=0.15,
            top_p=0.82,
            repetition_penalty=1.30,
            presence_penalty=0.3,
            is_active=True,
            is_visible=True,
        ),
    ]

    all_conditions = kimi_conditions + hermes_conditions

    print(f"Inserting {len(all_conditions)} new conditions...")
    for cond in all_conditions:
        print(f"  - {cond.slug}: {cond.label}")

    registered = engine.register_conditions(all_conditions)

    print(f"\nSuccessfully registered {len(registered)} conditions!")
    for cond in registered:
        print(f"  {cond.slug} (ID: {cond.id})")

if __name__ == "__main__":
    main()
