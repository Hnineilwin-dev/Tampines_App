import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# GROQ CLIENT
# ─────────────────────────────────────────
from groq import Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ─────────────────────────────────────────
# AGENT CONFIG
# ─────────────────────────────────────────
SENDGRID_API_KEY  = os.getenv("SENDGRID_API_KEY")
TWILIO_SID        = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN      = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE")
GOOGLE_SHEET_ID   = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
FROM_EMAIL        = os.getenv("FROM_EMAIL", "eaglee00011@gmail.com")
FROM_NAME         = "Tampines Estate Reporter"

DEMO_MODE  = os.getenv("DEMO_MODE", "false").lower() == "true"
TEST_MODE  = os.getenv("TEST_MODE", "false").lower() == "true"
TEST_EMAIL = os.getenv("TEST_EMAIL", "")
TEST_PHONE = os.getenv("TEST_PHONE", "")


# ─────────────────────────────────────────
# FULL 61-TYPE AGENCY ROUTING TABLE
# ─────────────────────────────────────────
AGENCY_ROUTING = {
    # ── CLEANLINESS (NEA / Town Council) ──────────────────────────────────
    "plastic_litter":       {"agency": "NEA / Town Council", "email": FROM_EMAIL, "sla": "24 hours",      "category": "cleanliness"},
    "food_waste":           {"agency": "NEA / Town Council", "email": FROM_EMAIL, "sla": "24 hours",      "category": "cleanliness"},
    "cigarette_butt":       {"agency": "NEA / Town Council", "email": FROM_EMAIL, "sla": "24 hours",      "category": "cleanliness"},
    "dry_leaves":           {"agency": "NEA / Town Council", "email": FROM_EMAIL, "sla": "24 hours",      "category": "cleanliness"},
    "bulky_item":           {"agency": "NEA / Town Council", "email": FROM_EMAIL, "sla": "48 hours",      "category": "cleanliness"},
    "high_rise_litter":     {"agency": "NEA / Town Council", "email": FROM_EMAIL, "sla": "24 hours",      "category": "cleanliness"},
    "overflowing_bin":      {"agency": "NEA / Town Council", "email": FROM_EMAIL, "sla": "4 hours",       "category": "cleanliness"},
    "illegal_dump":         {"agency": "NEA / Town Council", "email": FROM_EMAIL, "sla": "24 hours",      "category": "cleanliness"},

    # ── STRUCTURAL / MAINTENANCE (Town Council / HDB) ─────────────────────
    "broken_pipe":          {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "4 hours",       "category": "structural"},
    "broken_wire":          {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "4 hours",       "category": "structural"},
    "road_crack":           {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},
    "footpath_crack":       {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},
    "broken_drain":         {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "24 hours",      "category": "structural"},
    "broken_playground":    {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "24 hours",      "category": "structural"},
    "lift_fault":           {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "4 hours",       "category": "structural"},
    "broken_letterbox":     {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},
    "broken_railing":       {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "24 hours",      "category": "structural"},
    "wall_crack":           {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},
    "broken_sign":          {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},
    "broken_bench":         {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},
    "broken_shelter":       {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},
    "broken_bin":           {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},
    "damaged_cctv":         {"agency": "Town Council / HDB", "email": FROM_EMAIL, "sla": "3 working days","category": "structural"},

    # ── ELECTRICAL (SP Group / Town Council) ──────────────────────────────
    "streetlight_fault":    {"agency": "SP Group / Town Council", "email": FROM_EMAIL, "sla": "24 hours", "category": "electrical"},
    "carpark_light":        {"agency": "SP Group / Town Council", "email": FROM_EMAIL, "sla": "24 hours", "category": "electrical"},
    "power_box":            {"agency": "SP Group / Town Council", "email": FROM_EMAIL, "sla": "4 hours",  "category": "electrical"},
    "battery_waste":        {"agency": "SP Group / Town Council", "email": FROM_EMAIL, "sla": "24 hours", "category": "electrical"},
    "discarded_appliance":  {"agency": "SP Group / Town Council", "email": FROM_EMAIL, "sla": "24 hours", "category": "electrical"},

    # ── WATER / DRAINAGE (PUB / Town Council) ─────────────────────────────
    "flooding":             {"agency": "PUB / Town Council", "email": FROM_EMAIL, "sla": "IMMEDIATE",     "category": "water"},
    "choked_drain":         {"agency": "PUB / Town Council", "email": FROM_EMAIL, "sla": "4 hours",       "category": "water"},
    "manhole_overflow":     {"agency": "PUB / Town Council", "email": FROM_EMAIL, "sla": "4 hours",       "category": "water"},
    "ceiling_leak":         {"agency": "PUB / Town Council", "email": FROM_EMAIL, "sla": "24 hours",      "category": "water"},
    "stagnant_water":       {"agency": "PUB / Town Council", "email": FROM_EMAIL, "sla": "24 hours",      "category": "water"},

    # ── SAFETY / FIRE (SCDF / HDB / Police) ───────────────────────────────
    "blocked_exit":         {"agency": "SCDF / HDB / Police", "email": FROM_EMAIL, "sla": "IMMEDIATE",   "category": "safety"},
    "fire_hazard":          {"agency": "SCDF / HDB / Police", "email": FROM_EMAIL, "sla": "IMMEDIATE",   "category": "safety"},
    "fire_hose_reel":       {"agency": "SCDF / HDB / Police", "email": FROM_EMAIL, "sla": "4 hours",     "category": "safety"},
    "fallen_tree":          {"agency": "SCDF / HDB / Police", "email": FROM_EMAIL, "sla": "4 hours",     "category": "safety"},
    "graffiti":             {"agency": "SCDF / HDB / Police", "email": FROM_EMAIL, "sla": "3 working days","category": "safety"},

    # ── NOISE / NUISANCE (NEA / Police / CMC) ─────────────────────────────
    "renovation_noise":     {"agency": "NEA / Police / CMC", "email": FROM_EMAIL, "sla": "2 working days","category": "noise"},
    "neighbour_noise":      {"agency": "NEA / Police / CMC", "email": FROM_EMAIL, "sla": "2 working days","category": "noise"},
    "smoking_prohibited":   {"agency": "NEA / Police / CMC", "email": FROM_EMAIL, "sla": "24 hours",     "category": "noise"},
    "smoke_nuisance":       {"agency": "NEA / Police / CMC", "email": FROM_EMAIL, "sla": "24 hours",     "category": "noise"},
    "cooking_smell":        {"agency": "NEA / Police / CMC", "email": FROM_EMAIL, "sla": "2 working days","category": "noise"},

    # ── PEST / ANIMALS (NEA / NParks / AVS) ───────────────────────────────
    "rat":                  {"agency": "NEA / NParks / AVS", "email": FROM_EMAIL, "sla": "2 working days","category": "pest"},
    "pigeon":               {"agency": "NEA / NParks / AVS", "email": FROM_EMAIL, "sla": "2 working days","category": "pest"},
    "mosquito_breeding":    {"agency": "NEA / NParks / AVS", "email": FROM_EMAIL, "sla": "24 hours",     "category": "pest"},
    "stray_cat":            {"agency": "NEA / NParks / AVS", "email": FROM_EMAIL, "sla": "2 working days","category": "pest"},
    "cockroach":            {"agency": "NEA / NParks / AVS", "email": FROM_EMAIL, "sla": "2 working days","category": "pest"},
    "bee_nest":             {"agency": "NEA / NParks / AVS", "email": FROM_EMAIL, "sla": "4 hours",      "category": "pest"},
    "crow":                 {"agency": "NEA / NParks / AVS", "email": FROM_EMAIL, "sla": "2 working days","category": "pest"},

    # ── VEHICLES (LTA / HDB / URA) ────────────────────────────────────────
    "illegal_parking":      {"agency": "LTA / HDB / URA", "email": FROM_EMAIL, "sla": "24 hours",        "category": "vehicles"},
    "abandoned_vehicle":    {"agency": "LTA / HDB / URA", "email": FROM_EMAIL, "sla": "3 working days",  "category": "vehicles"},
    "footpath_obstruction": {"agency": "LTA / HDB / URA", "email": FROM_EMAIL, "sla": "24 hours",        "category": "vehicles"},
    "pmd":                  {"agency": "LTA / HDB / URA", "email": FROM_EMAIL, "sla": "24 hours",        "category": "vehicles"},
    "road_marking":         {"agency": "LTA / HDB / URA", "email": FROM_EMAIL, "sla": "3 working days",  "category": "vehicles"},
    "carpark_gantry":       {"agency": "LTA / HDB / URA", "email": FROM_EMAIL, "sla": "24 hours",        "category": "vehicles"},

    # ── GREENERY (NParks / Town Council) ──────────────────────────────────
    "overgrown_grass":        {"agency": "NParks / Town Council", "email": FROM_EMAIL, "sla": "3 working days","category": "greenery"},
    "fallen_uprooted_tree":   {"agency": "NParks / Town Council", "email": FROM_EMAIL, "sla": "4 hours",       "category": "greenery"},
    "dead_tree":              {"agency": "NParks / Town Council", "email": FROM_EMAIL, "sla": "3 working days", "category": "greenery"},
    "dry_leaves_accumulation":{"agency": "NParks / Town Council", "email": FROM_EMAIL, "sla": "3 working days", "category": "greenery"},
    "illegal_plant":          {"agency": "NParks / Town Council", "email": FROM_EMAIL, "sla": "5 working days", "category": "greenery"},
}

# Priority levels and their trigger keywords
PRIORITY_KEYWORDS = {
    "CRITICAL": ["fire", "smoke", "explosion", "collapse", "scdf", "emergency", "call 995", "unconscious", "trapped", "gas leak"],
    "HIGH":     ["electrical spark", "flooding", "flood", "exposed wire", "broken wire", "bee nest", "hornet", "bee swarm",
                 "blocked exit", "fire escape", "water rising", "lift stuck", "overflowing manhole"],
    "MEDIUM":   ["broken pipe", "water leak", "ceiling leak", "fallen tree", "pest", "rat", "mosquito",
                 "overflowing bin", "illegal dump", "pothole", "broken drain"],
    "LOW":      ["litter", "grass", "overgrown", "graffiti", "noise", "sign", "bench", "cctv", "shelter"],
}

PRIORITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]