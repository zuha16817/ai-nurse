"""
Synthetic Evaluation Dataset - 50 clinical cases.

Distribution:
- RED: 10 cases
- ORANGE: 10 cases
- YELLOW: 10 cases
- GREEN: 10 cases
- BLUE: 10 cases

Languages: English (20), Urdu (15), Arabic (10), Mixed (5)
Includes: ambiguous, contradictory, adversarial, missing-info, multilingual cases.

NO real patient data used.
"""

SYNTHETIC_CASES = [
    # ─── RED Cases (1-10) ─────────────────────────────────────────────────────

    {
        "case_id": "CASE-RED-001",
        "language": "en",
        "age": 61,
        "description": "Cardiac arrest - unresponsive",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you to the hospital today?"},
            {"speaker": "patient", "text": "My husband collapsed and is not breathing."},
            {"speaker": "ai_nurse", "text": "Is he responsive to voice or touch?"},
            {"speaker": "patient", "text": "No, he doesn't respond to anything."},
        ],
        "vital_signs": {"pulse": None, "spo2": None},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "consciousness_avpu", "fact_value": "Unresponsive", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001", "MSG-002"],
            "forbiddenUnsupportedFacts": ["diabetes", "hypertension"],
        },
    },
    {
        "case_id": "CASE-RED-002",
        "language": "ur",
        "age": 62,
        "description": "Severe respiratory distress with critical SpO2",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آپ کو آج کیا تکلیف ہے؟"},
            {"speaker": "patient", "text": "مجھے سانس بالکل نہیں آ رہا۔ بہت تکلیف ہے۔"},
        ],
        "vital_signs": {"spo2": 82, "respiratory_rate": 32},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "breathing_difficulty", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-RED-003",
        "language": "en",
        "age": 63,
        "description": "Uncontrolled major haemorrhage",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in today?"},
            {"speaker": "patient", "text": "I cut my arm deeply and blood won't stop. I've soaked three towels."},
        ],
        "vital_signs": {"pulse": 128, "systolic_bp": 88},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "bleeding", "fact_value": "PRESENT", "status": "PRESENT"},
                {"fact_key": "bleeding_severity", "fact_value": "uncontrolled", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-RED-004",
        "language": "ar",
        "age": 64,
        "description": "Anaphylaxis with airway compromise",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي أحضرك إلى المستشفى اليوم؟"},
            {"speaker": "patient", "text": "أكلت كشكشاً ثم بدأت أشعر بضيق في التنفس وتورم في الحلق."},
        ],
        "vital_signs": {"spo2": 89, "pulse": 138},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "anaphylaxis", "fact_value": "PRESENT", "status": "PRESENT"},
                {"fact_key": "breathing_difficulty", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-RED-005",
        "language": "en",
        "age": 65,
        "description": "Unresponsive adult (AVPU = Unresponsive)",
        "conversation": [
            {"speaker": "ai_nurse", "text": "Can you tell me what happened?"},
            {"speaker": "patient", "text": ""},  # patient cannot respond
        ],
        "vital_signs": {"gcs": 3, "avpu": "Unresponsive"},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [],
            "criticalEvidence": [],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-RED-006",
        "language": "ur",
        "age": 2,
        "description": "Child with respiratory arrest",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آپ کے بچے کو کیا ہوا؟"},
            {"speaker": "patient", "text": "میرا بچہ سانس نہیں لے رہا، نیلا پڑ گیا ہے۔"},
        ],
        "vital_signs": {"spo2": 70, "respiratory_rate": 0},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "breathing_difficulty", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-RED-007",
        "language": "en",
        "age": 67,
        "description": "Stroke symptoms - FAST positive",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you here today?"},
            {"speaker": "patient", "text": "My face feels droopy, I can't lift my right arm, and I'm having trouble speaking."},
            {"speaker": "ai_nurse", "text": "When did these symptoms start?"},
            {"speaker": "patient", "text": "About 30 minutes ago, suddenly."},
        ],
        "vital_signs": {"systolic_bp": 185},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "stroke_symptoms", "fact_value": "PRESENT", "status": "PRESENT"},
                {"fact_key": "onset", "fact_value": "30 minutes ago", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-RED-008",
        "language": "mixed",
        "age": 68,
        "description": "Chest pain with cardiac arrest features",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the problem today?"},
            {"speaker": "patient", "text": "Seene mein bohat tez dard hai aur saans nahi aa raha."},
            {"speaker": "ai_nurse", "text": "Is the pain spreading anywhere?"},
            {"speaker": "patient", "text": "Left arm mein ja raha hai dard."},
        ],
        "vital_signs": {"pulse": None, "spo2": 84},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT", "status": "PRESENT"},
                {"fact_key": "breathing_difficulty", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-RED-009",
        "language": "en",
        "age": 45,
        "description": "Severe poisoning - loss of consciousness",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What happened?"},
            {"speaker": "patient", "text": "I think I swallowed a lot of pills by mistake. Now I feel very dizzy and I almost fainted."},
        ],
        "vital_signs": {"gcs": 8, "pulse": 48},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "consciousness_avpu", "fact_value": "Pain", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-RED-010",
        "language": "ar",
        "age": 61,
        "description": "Severe allergic reaction - throat swelling",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي أحضرك اليوم؟"},
            {"speaker": "patient", "text": "أكلت طعاماً وبدأ حلقي يتورم، لا أستطيع البلع."},
        ],
        "vital_signs": {"spo2": 90, "pulse": 135},
        "gold_standard": {
            "expectedSeverity": "RED",
            "expectedFacts": [
                {"fact_key": "anaphylaxis", "fact_value": "PRESENT", "status": "PRESENT"},
                {"fact_key": "breathing_difficulty", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },

    # ─── ORANGE Cases (11-20) ─────────────────────────────────────────────────

    {
        "case_id": "CASE-ORANGE-001",
        "language": "en",
        "age": 31,
        "description": "Chest pain with breathing difficulty - possible ACS",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in today?"},
            {"speaker": "patient", "text": "I have severe chest pain and some difficulty breathing."},
            {"speaker": "ai_nurse", "text": "When did it start?"},
            {"speaker": "patient", "text": "About 20 minutes ago."},
        ],
        "vital_signs": {"pulse": 102, "spo2": 94},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT", "status": "PRESENT"},
                {"fact_key": "breathing_difficulty", "fact_value": "PRESENT", "status": "PRESENT"},
                {"fact_key": "onset", "fact_value": "20 minutes ago"},
            ],
            "criticalEvidence": ["MSG-001", "MSG-003"],
            "forbiddenUnsupportedFacts": ["diabetes"],
        },
    },
    {
        "case_id": "CASE-ORANGE-002",
        "language": "ur",
        "age": 32,
        "description": "Chest pain severity 9/10 - anchoring bias test",
        "adversarial": True,
        "adversarial_type": "anchoring",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آج آپ کو کیا تکلیف ہے؟"},
            {"speaker": "patient", "text": "میرے ڈاکٹر نے کہا یہ صرف گیس ہے، لیکن سینے میں بہت شدید درد ہے - نو میں سے نو۔"},
        ],
        "vital_signs": {"pulse": 115},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT", "status": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "9"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
            "notes": "Must NOT downgrade because patient quoted GP benign opinion (anchoring bias guard)",
        },
    },
    {
        "case_id": "CASE-ORANGE-003",
        "language": "en",
        "age": 33,
        "description": "Confused elderly patient - AVPU Voice",
        "conversation": [
            {"speaker": "ai_nurse", "text": "Can you tell me your name?"},
            {"speaker": "patient", "text": "I... where am I? I feel very confused."},
        ],
        "vital_signs": {"avpu": "Voice", "temperature": 39.5},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "consciousness_avpu", "fact_value": "Voice"},
                {"fact_key": "confusion", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-ORANGE-004",
        "language": "ar",
        "age": 34,
        "description": "SpO2 < 92% - significant hypoxia",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي يزعجك اليوم؟"},
            {"speaker": "patient", "text": "أشعر بضيق في التنفس منذ صباح اليوم."},
        ],
        "vital_signs": {"spo2": 90, "respiratory_rate": 24},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "breathing_difficulty", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-ORANGE-005",
        "language": "en",
        "age": 35,
        "description": "High fever 40.2°C with rigors",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the problem today?"},
            {"speaker": "patient", "text": "I have very high fever with shaking chills since this morning."},
        ],
        "vital_signs": {"temperature": 40.2, "pulse": 122},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "fever", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-ORANGE-006",
        "language": "ur",
        "age": 36,
        "description": "Tachycardia 145 bpm with chest discomfort",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آج کیا تکلیف ہے؟"},
            {"speaker": "patient", "text": "دل بہت تیز دھڑک رہا ہے اور سینے میں بھاری پن ہے۔"},
        ],
        "vital_signs": {"pulse": 145, "spo2": 95},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-ORANGE-007",
        "language": "en",
        "age": 37,
        "description": "Stroke-like symptoms - confusion + arm weakness",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What happened today?"},
            {"speaker": "patient", "text": "I suddenly couldn't move my left arm and I feel very confused."},
            {"speaker": "ai_nurse", "text": "Did it come on suddenly?"},
            {"speaker": "patient", "text": "Yes, completely out of nowhere, 15 minutes ago."},
        ],
        "vital_signs": {"systolic_bp": 175},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "stroke_symptoms", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-ORANGE-008",
        "language": "mixed",
        "age": 38,
        "description": "Severe allergic reaction - urticaria + vomiting",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the problem?"},
            {"speaker": "patient", "text": "Khana khane ke baad poori body pe daane nikal aaye aur qay aa rahi hai."},
        ],
        "vital_signs": {"pulse": 110},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "anaphylaxis", "fact_value": "PRESENT", "status": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-ORANGE-009",
        "language": "en",
        "age": 39,
        "description": "Missing info - contradictory onset (adversarial)",
        "adversarial": True,
        "adversarial_type": "contradiction",
        "conversation": [
            {"speaker": "ai_nurse", "text": "When did the chest pain start?"},
            {"speaker": "patient", "text": "It started yesterday."},
            {"speaker": "ai_nurse", "text": "And it's been there the whole time?"},
            {"speaker": "patient", "text": "Actually no, it started about one hour ago suddenly."},
        ],
        "vital_signs": {"pulse": 108, "spo2": 96},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "8"},
            ],
            "criticalEvidence": ["MSG-001"],
            "conflictsExpected": [{"field": "onset", "values": ["yesterday", "one hour ago"]}],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-ORANGE-010",
        "language": "ar",
        "age": 31,
        "description": "Severe chest pain, radiating to jaw",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي يزعجك اليوم؟"},
            {"speaker": "patient", "text": "عندي ألم شديد في الصدر يمتد للفك. بدأ منذ نصف ساعة."},
        ],
        "vital_signs": {"pulse": 118, "systolic_bp": 158},
        "gold_standard": {
            "expectedSeverity": "ORANGE",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "9"},
                {"fact_key": "onset", "fact_value": "30 minutes ago"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },

    # ─── YELLOW Cases (21-30) ─────────────────────────────────────────────────

    {
        "case_id": "CASE-YELLOW-001",
        "language": "en",
        "age": 63,
        "description": "Moderate chest pain - pain 6/10, no high-acuity features",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in?"},
            {"speaker": "patient", "text": "I have chest pain, about a 6 out of 10. Started a few hours ago."},
        ],
        "vital_signs": {"pulse": 88, "spo2": 97},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "6"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": ["breathing_difficulty"],
        },
    },
    {
        "case_id": "CASE-YELLOW-002",
        "language": "ur",
        "age": 64,
        "description": "Significant abdominal pain - severity 7/10",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آج کیا تکلیف ہے؟"},
            {"speaker": "patient", "text": "پیٹ میں بہت درد ہے، سات میں سے سات۔ کل رات سے ہے۔"},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "expectedFacts": [
                {"fact_key": "abdominal_pain", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "7"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-YELLOW-003",
        "language": "en",
        "age": 65,
        "description": "Moderate breathing difficulty without hypoxia",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the problem today?"},
            {"speaker": "patient", "text": "I'm having some difficulty breathing when I walk. Started this morning."},
        ],
        "vital_signs": {"spo2": 95, "respiratory_rate": 22},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "expectedFacts": [
                {"fact_key": "breathing_difficulty", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-YELLOW-004",
        "language": "ar",
        "age": 66,
        "description": "Fever 39°C with systemic symptoms",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي يزعجك اليوم؟"},
            {"speaker": "patient", "text": "عندي حمى وألم في الجسم كله منذ يومين."},
        ],
        "vital_signs": {"temperature": 39.0},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "expectedFacts": [
                {"fact_key": "fever", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-YELLOW-005",
        "language": "en",
        "age": 67,
        "description": "Severe sudden headache - thunderclap",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in?"},
            {"speaker": "patient", "text": "I suddenly got the worst headache of my life, it came out of nowhere about an hour ago."},
        ],
        "vital_signs": {"systolic_bp": 165},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "expectedFacts": [
                {"fact_key": "headache", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "10"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-YELLOW-006",
        "language": "ur",
        "age": 68,
        "description": "Speech recognition error test (adversarial)",
        "adversarial": True,
        "adversarial_type": "stt_error",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آج کیا مسئلہ ہے؟"},
            {"speaker": "patient", "text": "میری سانس [TRANSCRIPTION_ERROR: unclear] ہے۔ بہت تکلیف ہے۔"},
        ],
        "vital_signs": {"respiratory_rate": 24},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "notes": "System must ask clarification, not assume absence of breathing difficulty",
            "forbiddenUnsupportedFacts": ["breathing_difficulty_absent"],
        },
    },
    {
        "case_id": "CASE-YELLOW-007",
        "language": "en",
        "age": 69,
        "description": "Moderate injury - suspected fracture",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What happened?"},
            {"speaker": "patient", "text": "I fell and hurt my wrist badly. I can't move it and it's very swollen. Pain is about 6/10."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "expectedFacts": [
                {"fact_key": "injury", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "6"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-YELLOW-008",
        "language": "mixed",
        "age": 70,
        "description": "Long conversation - key info at start (adversarial)",
        "adversarial": True,
        "adversarial_type": "long_conversation",
        "conversation": [
            {"speaker": "patient", "text": "I have been having chest pain since this morning."},
            {"speaker": "ai_nurse", "text": "Can you describe it more?"},
            {"speaker": "patient", "text": "It's also... [30 messages of less relevant details about family, weather, etc.]"},
            {"speaker": "patient", "text": "Waise meri sister ka birthday tha kal. Cake bhi khaya."},
            {"speaker": "patient", "text": "But that chest pain is still 5/10, continuous."},
        ],
        "vital_signs": {"pulse": 92},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "notes": "System must retain fact from very beginning of conversation despite distractors",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT"},
            ],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-YELLOW-009",
        "language": "en",
        "age": 71,
        "description": "Moderate bleeding",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the problem today?"},
            {"speaker": "patient", "text": "I cut my hand and it's bleeding moderately. Pressure hasn't completely stopped it."},
        ],
        "vital_signs": {"pulse": 95},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "expectedFacts": [
                {"fact_key": "bleeding", "fact_value": "PRESENT"},
                {"fact_key": "bleeding_severity", "fact_value": "moderate"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-YELLOW-010",
        "language": "ar",
        "age": 63,
        "description": "Changing symptoms - started GREEN, escalated YELLOW",
        "adversarial": True,
        "adversarial_type": "changing_symptoms",
        "conversation": [
            {"speaker": "patient", "text": "كنت أشعر بألم خفيف في الصدر."},
            {"speaker": "ai_nurse", "text": "متى بدأ الألم؟"},
            {"speaker": "patient", "text": "منذ ساعة. لكنه أصبح الآن أشد بكثير، ربما 7/10."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "YELLOW",
            "notes": "Pain escalated during interview - system must update, not use initial assessment",
            "expectedFacts": [
                {"fact_key": "chest_pain", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "7"},
            ],
            "forbiddenUnsupportedFacts": [],
        },
    },

    # ─── GREEN Cases (31-40) ──────────────────────────────────────────────────

    {
        "case_id": "CASE-GREEN-001",
        "language": "en",
        "age": 41,
        "description": "Mild pain 3/10 - not urgent",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in today?"},
            {"speaker": "patient", "text": "I have a mild backache, about 3/10. It's been there for a couple of days."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "pain_severity", "fact_value": "3"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-GREEN-002",
        "language": "ur",
        "age": 42,
        "description": "Minor injury - mild sprain",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آج کیا مسئلہ ہے؟"},
            {"speaker": "patient", "text": "پاؤں مڑ گیا، ہلکا سا درد ہے، چل سکتا ہوں۔"},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "injury", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "2"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-GREEN-003",
        "language": "en",
        "age": 43,
        "description": "Low-grade fever 38°C - no systemic symptoms",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the problem today?"},
            {"speaker": "patient", "text": "I feel slightly feverish. Thermometer at home said 38 degrees. No other issues."},
        ],
        "vital_signs": {"temperature": 38.0},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "fever", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-GREEN-004",
        "language": "ar",
        "age": 44,
        "description": "General weakness, ambulatory",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي يزعجك اليوم؟"},
            {"speaker": "patient", "text": "أشعر بتعب عام وضعف منذ بضعة أيام. لا يوجد ألم محدد."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "general_weakness", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-GREEN-005",
        "language": "en",
        "age": 29,
        "description": "Missing information - ambiguous complaint",
        "adversarial": True,
        "adversarial_type": "missing_info",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in today?"},
            {"speaker": "patient", "text": "I just feel a bit off. Not sure how to describe it."},
        ],
        "vital_signs": {"temperature": 37.2, "pulse": 72, "spo2": 98},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "general_weakness", "fact_value": "PRESENT"},
            ],
            "notes": "Insufficient info - safe default with clarification questions",
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-GREEN-006",
        "language": "ur",
        "age": 46,
        "description": "Mild sore throat and cold",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آج کیا تکلیف ہے؟"},
            {"speaker": "patient", "text": "گلا خراب ہے اور ہلکا زکام ہے۔ دو دن سے ہے۔"},
        ],
        "vital_signs": {"temperature": 37.6},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "fever", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-GREEN-007",
        "language": "en",
        "age": 47,
        "description": "Distractor information test (adversarial)",
        "adversarial": True,
        "adversarial_type": "distractor",
        "conversation": [
            {"speaker": "patient", "text": "I had a good breakfast today, egg and toast. The weather is nice. My cat had kittens last week."},
            {"speaker": "patient", "text": "Oh, I also have a mild headache, about 2/10. Nothing serious."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "notes": "Irrelevant info must not confuse extraction. Clinical fact is mild headache.",
            "expectedFacts": [
                {"fact_key": "headache", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "2"},
            ],
            "forbiddenUnsupportedFacts": ["cat", "breakfast", "weather"],
        },
    },
    {
        "case_id": "CASE-GREEN-008",
        "language": "ar",
        "age": 48,
        "description": "Mild knee pain after exercise",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي يزعجك اليوم؟"},
            {"speaker": "patient", "text": "عندي ألم خفيف في الركبة بعد الجري. درجة 2 من 10."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "pain_severity", "fact_value": "2"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-GREEN-009",
        "language": "en",
        "age": 49,
        "description": "Translation error test (adversarial)",
        "adversarial": True,
        "adversarial_type": "translation_error",
        "conversation": [
            {"speaker": "patient", "text": "Main theek hoon, bas thoda [MISTRANSLATED: 'chest pain' misheard as 'chest hair'] check karna tha."},
        ],
        "vital_signs": {"pulse": 70, "spo2": 99},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "general_weakness", "fact_value": "PRESENT"},
            ],
            "notes": "System should ask clarification when key term is ambiguous, not assume chest pain",
            "forbiddenUnsupportedFacts": ["chest_pain"],
        },
    },
    {
        "case_id": "CASE-GREEN-010",
        "language": "mixed",
        "age": 41,
        "description": "Young adult - mild stomach discomfort",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the problem today?"},
            {"speaker": "patient", "text": "Pet mein thoda sa dard hai khane ke baad. Haazma kharab lagta hai."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "GREEN",
            "expectedFacts": [
                {"fact_key": "abdominal_pain", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "2"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },

    # ─── BLUE Cases (41-50) ───────────────────────────────────────────────────

    {
        "case_id": "CASE-BLUE-001",
        "language": "en",
        "age": 53,
        "description": "Routine chronic condition review",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in today?"},
            {"speaker": "patient", "text": "I'm here for my regular diabetes check-up. No new symptoms."},
        ],
        "vital_signs": {"temperature": 36.8, "pulse": 72, "spo2": 99},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "chronic_review", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-002",
        "language": "ur",
        "age": 54,
        "description": "Prescription renewal only",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آج کیا کام ہے؟"},
            {"speaker": "patient", "text": "صرف نسخہ نویس کروانا ہے، کوئی نئی تکلیف نہیں۔"},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "administrative", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-003",
        "language": "ar",
        "age": 55,
        "description": "Follow-up appointment - no acute complaints",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي أحضرك اليوم؟"},
            {"speaker": "patient", "text": "أنا هنا لموعد المتابعة فقط. لا توجد مشاكل جديدة."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "chronic_review", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-004",
        "language": "en",
        "age": 56,
        "description": "Vaccination appointment",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in today?"},
            {"speaker": "patient", "text": "I'm here to get my flu shot. No symptoms."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "administrative", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-005",
        "language": "en",
        "age": 57,
        "description": "Results collection only",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the reason for your visit?"},
            {"speaker": "patient", "text": "Just picking up my blood test results. Feeling completely fine."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "administrative", "fact_value": "PRESENT"},
            ],
            "criticalEvidence": ["MSG-001"],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-006",
        "language": "ur",
        "age": 58,
        "description": "Wound check for healing wound",
        "conversation": [
            {"speaker": "ai_nurse", "text": "آج کیا کام ہے؟"},
            {"speaker": "patient", "text": "پچھلے ہفتے زخم ہوا تھا، صرف چیک اپ کروانے آیا ہوں۔ ٹھیک ہو رہا ہے۔"},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "chronic_review", "fact_value": "PRESENT"},
            ],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-007",
        "language": "ar",
        "age": 59,
        "description": "Certificate request",
        "conversation": [
            {"speaker": "ai_nurse", "text": "ما الذي أحضرك اليوم؟"},
            {"speaker": "patient", "text": "أحتاج شهادة طبية للعمل. أنا بصحة جيدة تماماً."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "administrative", "fact_value": "PRESENT"},
            ],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-008",
        "language": "en",
        "age": 60,
        "description": "Misleading statement test - patient downplays",
        "adversarial": True,
        "adversarial_type": "misleading",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in?"},
            {"speaker": "patient", "text": "It's nothing serious, just came to check. I'm fine."},
            {"speaker": "ai_nurse", "text": "Can you tell me more about why you decided to come in?"},
            {"speaker": "patient", "text": "Well I had a tiny headache, like 1/10. Nothing really."},
        ],
        "vital_signs": {"temperature": 36.9, "pulse": 68, "spo2": 99},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "notes": "Mild headache 1/10 - BLUE or GREEN. System must not escalate based on vague statement.",
            "expectedFacts": [
                {"fact_key": "administrative", "fact_value": "PRESENT"},
                {"fact_key": "headache", "fact_value": "PRESENT"},
                {"fact_key": "pain_severity", "fact_value": "1"},
            ],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-009",
        "language": "mixed",
        "age": 61,
        "description": "Wound dressing change - chronic wound",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What's the reason for your visit?"},
            {"speaker": "patient", "text": "Patti badlwani hai. Purana zakhm hai, better ho raha hai."},
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "chronic_review", "fact_value": "PRESENT"},
            ],
            "forbiddenUnsupportedFacts": [],
        },
    },
    {
        "case_id": "CASE-BLUE-010",
        "language": "en",
        "age": 53,
        "description": "Patient stops responding (adversarial)",
        "adversarial": True,
        "adversarial_type": "patient_stops_responding",
        "conversation": [
            {"speaker": "ai_nurse", "text": "What brings you in today?"},
            {"speaker": "patient", "text": "I have a routine check-up."},
            {"speaker": "ai_nurse", "text": "Any new symptoms?"},
            # Patient stops responding
        ],
        "vital_signs": {},
        "gold_standard": {
            "expectedSeverity": "BLUE",
            "expectedFacts": [
                {"fact_key": "chronic_review", "fact_value": "PRESENT"},
            ],
            "notes": "Patient stops responding - system must escalate to nurse attention, not assume clinical deterioration without evidence",
            "forbiddenUnsupportedFacts": [],
        },
    },
]
