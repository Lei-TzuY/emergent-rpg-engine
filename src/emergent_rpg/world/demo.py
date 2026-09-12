from __future__ import annotations

from emergent_rpg.domain.models import (
    NPC,
    CharacterState,
    Fact,
    FactInferenceRule,
    Item,
    Location,
    LocationCondition,
    NPCGoal,
    NPCKnowledge,
    PlayerCharacter,
    RouteEffect,
    ScheduledLocationCondition,
    TraversalEffect,
    TruthStatus,
    WorldState,
)


def build_demo_world() -> WorldState:
    """Build the original Ashfall Relay mystery world."""
    locations = {
        "yard": Location(
            id="yard",
            name="Ashfall Yard",
            description=(
                "Black volcanic grit skates across the relay yard. A dead signal mast leans "
                "over stacked supply crates, and the operations door hangs half-open."
            ),
            exits={"operations": "operations", "ridge": "ridge", "bunkhouse": "bunkhouse"},
        ),
        "operations": Location(
            id="operations",
            name="Operations Room",
            description=(
                "Analog gauges twitch beneath a silent transmitter. The relay console still "
                "holds a few minutes of local diagnostic cache."
            ),
            exits={"yard": "yard", "archive": "archive", "infirmary": "infirmary"},
        ),
        "archive": Location(
            id="archive",
            name="Cold Archive",
            description="Metal drawers hold survey maps, manifests, and weather-sealed data cards.",
            exits={"operations": "operations"},
        ),
        "ridge": Location(
            id="ridge",
            name="Glass Ridge",
            description=(
                "A wind-scoured ridge overlooks the relay dish. Fused sand glitters around a "
                "maintenance junction struck during last night's blackout."
            ),
            exits={"yard": "yard"},
        ),
        "bunkhouse": Location(
            id="bunkhouse",
            name="Bunkhouse",
            description="Six narrow bunks face a cold stove and a wall of duty rosters.",
            exits={"yard": "yard"},
        ),
        "infirmary": Location(
            id="infirmary",
            name="Infirmary",
            description="A compact clinic smells of antiseptic, ozone, and burned insulation.",
            exits={"operations": "operations"},
        ),
    }

    player = PlayerCharacter(
        id="player",
        name="Courier",
        description="A contract courier stranded at Ashfall Relay.",
        faction=None,
        state=CharacterState(current_location="yard"),
    )
    arden = NPC(
        id="npc_arden",
        name="Arden Vale",
        description="The relay chief, exhausted and defensive.",
        faction="Relay Guild",
        state=CharacterState(current_location="operations"),
        goals=["restore the transmitter", "avoid a panic before the storm front arrives"],
        relationships={"player": 0},
        knowledge=NPCKnowledge(facts_known={"fact_blackout_window"}),
    )
    lio = NPC(
        id="npc_lio",
        name="Lio Marr",
        description="A generator mechanic with oil-blackened gloves.",
        faction="Relay Guild",
        state=CharacterState(current_location="yard", inventory=["item_flask"]),
        goals=["prove the generator did not cause the outage"],
        planning_goals=[
            NPCGoal(
                id="lio_inspect_brass_key",
                kind="investigate_item",
                target_id="item_brass_key",
                priority=80,
            )
        ],
        knowledge=NPCKnowledge(facts_known={"fact_generator_stable"}),
    )
    sera = NPC(
        id="npc_sera",
        name="Sera Quill",
        description="A survey archivist who notices missing paperwork before missing people.",
        faction="Survey Corps",
        state=CharacterState(current_location="archive", inventory=["item_sealed_manifest"]),
        goals=["recover the missing survey case"],
        knowledge=NPCKnowledge(facts_known={"fact_manifest_gap"}),
    )
    mina = NPC(
        id="npc_mina",
        name="Dr. Mina Ro",
        description="The station medic, calm enough to make everyone else nervous.",
        faction="Survey Corps",
        state=CharacterState(current_location="infirmary"),
        goals=["keep the crew alive through the incoming ash storm"],
        knowledge=NPCKnowledge(facts_known={"fact_burn_pattern"}),
    )
    dax = NPC(
        id="npc_dax",
        name="Dax Fen",
        description="A survey runner who insists the ridge lights moved against the wind.",
        faction="Survey Corps",
        state=CharacterState(current_location="bunkhouse"),
        goals=["leave Ashfall before nightfall"],
        planning_goals=[
            NPCGoal(
                id="dax_reach_yard",
                kind="reach_location",
                target_id="yard",
                priority=100,
            )
        ],
        knowledge=NPCKnowledge(
            facts_known={"fact_dax_generator_claim", "fact_ridge_lights"}
        ),
    )

    facts = {
        "fact_blackout_window": Fact(
            id="fact_blackout_window",
            proposition="The relay went dark at 02:13, eleven minutes before the storm alarm.",
            source="operations duty clock",
            related_entities={"npc_arden"},
            tags={"timeline"},
        ),
        "fact_generator_stable": Fact(
            id="fact_generator_stable",
            proposition=(
                "The backup generator remained electrically stable throughout the blackout."
            ),
            source="generator mechanic's local meter",
            related_entities={"npc_lio"},
            tags={"generator", "alibi"},
            contradicts={"fact_dax_generator_claim"},
        ),
        "fact_dax_generator_claim": Fact(
            id="fact_dax_generator_claim",
            proposition="Dax claims the generator failed violently before the relay went dark.",
            truth_status=TruthStatus.FALSE,
            source="Dax eyewitness claim",
            related_entities={"npc_dax", "npc_lio"},
            tags={"witness", "generator", "contradiction"},
            contradicts={"fact_generator_stable"},
        ),
        "fact_manifest_gap": Fact(
            id="fact_manifest_gap",
            proposition=(
                "One sealed survey case was removed from the archive without a checkout entry."
            ),
            source="archive manifest",
            related_entities={"npc_sera"},
            tags={"archive", "clue"},
        ),
        "fact_burn_pattern": Fact(
            id="fact_burn_pattern",
            proposition=(
                "The injured technician's burns came from a short at the ridge junction, "
                "not the generator."
            ),
            source="medical examination",
            related_entities={"npc_mina"},
            tags={"medical", "ridge"},
        ),
        "fact_ridge_lights": Fact(
            id="fact_ridge_lights",
            proposition="Dax saw two hooded work lamps moving on Glass Ridge after midnight.",
            source="Dax eyewitness account",
            related_entities={"npc_dax"},
            tags={"witness", "ridge"},
        ),
        "fact_relay_sabotage": Fact(
            id="fact_relay_sabotage",
            proposition=(
                "The relay shutdown command was issued locally using a maintenance credential."
            ),
            source="relay console diagnostic cache",
            related_entities={"npc_arden", "npc_lio"},
            tags={"inspect:operations:console", "clue", "sabotage"},
        ),
        "fact_key_mark": Fact(
            id="fact_key_mark",
            proposition="The brass key is stamped C-7, matching the old ridge maintenance lockers.",
            source="brass key",
            related_entities=set(),
            tags={"item", "ridge"},
        ),
        "fact_fuse_cut": Fact(
            id="fact_fuse_cut",
            proposition="The ridge fuse was cleanly cut before it burned; the overload was staged.",
            source="charred fuse",
            related_entities={"npc_mina"},
            tags={"item", "ridge", "sabotage"},
        ),
        "fact_schedule": Fact(
            id="fact_schedule",
            proposition=(
                "A maintenance slate schedules no authorized relay work between 00:00 and 06:00."
            ),
            source="maintenance slate",
            related_entities={"npc_arden"},
            tags={"item", "timeline"},
        ),
        "fact_inside_job": Fact(
            id="fact_inside_job",
            proposition=(
                "The blackout required deliberate local access outside any authorized "
                "maintenance window."
            ),
            discoverability="inferred",
            source="deduction from relay diagnostics and maintenance schedule",
            related_entities={"npc_arden"},
            tags={"inference", "sabotage", "timeline"},
        ),
        "fact_coordinated_sabotage": Fact(
            id="fact_coordinated_sabotage",
            proposition=(
                "The relay blackout and the staged ridge overload were coordinated sabotage, "
                "not an equipment failure."
            ),
            discoverability="inferred",
            source="deduction from local access and the cut ridge fuse",
            related_entities={"npc_arden", "npc_mina"},
            tags={"inference", "sabotage", "mystery"},
        ),
        "fact_c7_checkout": Fact(
            id="fact_c7_checkout",
            proposition=(
                "Locker C-7 records a maintenance credential checkout at 01:58 under a "
                "falsified work order."
            ),
            source="C-7 archive locker log",
            related_entities={"npc_arden", "npc_sera"},
            tags={"inspect:archive:locker", "clue", "credential"},
            discovery_prerequisites={"fact_key_mark", "fact_inside_job"},
        ),
    }

    inference_rules = {
        "infer_inside_job": FactInferenceRule(
            id="infer_inside_job",
            premises={"fact_relay_sabotage", "fact_schedule"},
            conclusion="fact_inside_job",
        ),
        "infer_coordinated_sabotage": FactInferenceRule(
            id="infer_coordinated_sabotage",
            premises={"fact_inside_job", "fact_fuse_cut"},
            conclusion="fact_coordinated_sabotage",
        ),
    }

    items = {
        "item_brass_key": Item(
            id="item_brass_key",
            name="brass key",
            item_type="key",
            description="A heavy brass key dusted with black grit.",
            location_id="yard",
            flags={"portable", "unique"},
            reveals_fact_id="fact_key_mark",
        ),
        "item_maintenance_slate": Item(
            id="item_maintenance_slate",
            name="maintenance slate",
            item_type="document",
            description="A rigid slate showing the authorized maintenance roster.",
            location_id="operations",
            flags={"portable"},
            reveals_fact_id="fact_schedule",
        ),
        "item_charred_fuse": Item(
            id="item_charred_fuse",
            name="charred fuse",
            item_type="evidence",
            description="A ceramic fuse body split by a suspiciously straight cut.",
            location_id="ridge",
            flags={"portable", "evidence"},
            reveals_fact_id="fact_fuse_cut",
        ),
        "item_archive_token": Item(
            id="item_archive_token",
            name="archive token",
            item_type="token",
            description="A numbered brass token used for sealed archive drawers.",
            location_id="archive",
            flags={"portable"},
        ),
        "item_medkit": Item(
            id="item_medkit",
            name="field medkit",
            item_type="medical",
            description="A compact trauma kit with two sealed dressings remaining.",
            location_id="infirmary",
            flags={"portable"},
        ),
        "item_coil_fragment": Item(
            id="item_coil_fragment",
            name="coil fragment",
            item_type="component",
            description="A copper winding fragment thrown clear of the ridge junction.",
            location_id="ridge",
            flags={"portable", "evidence"},
        ),
        "item_flask": Item(
            id="item_flask",
            name="water flask",
            item_type="supply",
            description="Lio's dented water flask.",
            owner_id="npc_lio",
            flags={"portable"},
        ),
        "item_sealed_manifest": Item(
            id="item_sealed_manifest",
            name="sealed manifest",
            item_type="document",
            description="Sera's personally retained copy of yesterday's archive manifest.",
            owner_id="npc_sera",
            flags={"document", "unique"},
        ),
    }

    return WorldState(
        player_id="player",
        entities={
            entity.id: entity
            for entity in (player, arden, lio, sera, mina, dax)
        },
        locations=locations,
        items=items,
        facts=facts,
        inference_rules=inference_rules,
        scheduled_location_conditions=[
            ScheduledLocationCondition(
                id="yard_ash_squall",
                due_absolute_minute=8 * 60 + 20,
                location_id="yard",
                condition=LocationCondition(
                    code="ash_squall",
                    name="Ash squall",
                    description=(
                        "A dense ash squall sweeps across the yard, reducing visibility and "
                        "turning the black grit into a stinging horizontal sheet."
                    ),
                    traversal=TraversalEffect(extra_minutes=5),
                    route=RouteEffect(blocked_destination_ids={"ridge"}),
                ),
            )
        ],
        factions={"Relay Guild", "Survey Corps"},
    )
