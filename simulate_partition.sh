#!/usr/bin/env bash
# =============================================================================
# simulate_partition.sh
#
# Demonstrates network partition scenario and vector clock conflict detection
# in the Multi-Region Incident Management System.
#
# Prerequisites:
#   - docker-compose up has been run and all services are healthy
#   - curl and jq are installed
#
# Usage:
#   chmod +x simulate_partition.sh
#   ./simulate_partition.sh
# =============================================================================

set -euo pipefail

US="http://localhost:8001"
EU="http://localhost:8002"
APAC="http://localhost:8003"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_step() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}STEP $1: $2${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_info()    { echo -e "${GREEN}  ✔  $1${NC}"; }
log_warn()    { echo -e "${YELLOW}  ⚠  $1${NC}"; }
log_json()    { echo "$1" | jq '.'; }

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Multi-Region Incident Management — Partition Demo  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── STEP 1: Create incident in region-us ────────────────────────────────────
log_step 1 "Creating incident in region-us"

INCIDENT=$(curl -sf -X POST "$US/incidents" \
    -H "Content-Type: application/json" \
    -d '{"title":"Global DNS Outage","description":"DNS resolution failing across all zones","severity":"CRITICAL"}')

INCIDENT_ID=$(echo "$INCIDENT" | jq -r '.id')
VC_INITIAL=$(echo "$INCIDENT" | jq '.vector_clock')

log_info "Created incident ID: $INCIDENT_ID"
log_info "Initial vector clock: $VC_INITIAL"

# ─── STEP 2: Wait for auto-replication to all regions ────────────────────────
log_step 2 "Waiting 12s for automatic replication to region-eu and region-apac"
sleep 12

EU_INCIDENT=$(curl -sf "$EU/incidents/$INCIDENT_ID" 2>/dev/null || echo "null")
APAC_INCIDENT=$(curl -sf "$APAC/incidents/$INCIDENT_ID" 2>/dev/null || echo "null")

if [ "$EU_INCIDENT" = "null" ] || [ "$(echo "$EU_INCIDENT" | jq -r '.id // empty')" = "" ]; then
    log_warn "Incident not yet in EU — triggering manual replication"
    curl -sf -X POST "$EU/internal/replicate" \
        -H "Content-Type: application/json" \
        -d "$INCIDENT" > /dev/null
fi

if [ "$APAC_INCIDENT" = "null" ] || [ "$(echo "$APAC_INCIDENT" | jq -r '.id // empty')" = "" ]; then
    log_warn "Incident not yet in APAC — triggering manual replication"
    curl -sf -X POST "$APAC/internal/replicate" \
        -H "Content-Type: application/json" \
        -d "$INCIDENT" > /dev/null
fi

log_info "Incident replicated to all regions"

# ─── STEP 3: Verify all regions have the incident ────────────────────────────
log_step 3 "Verifying incident exists in all regions"
EU_VC=$(curl -sf "$EU/incidents/$INCIDENT_ID" | jq '.vector_clock')
APAC_VC=$(curl -sf "$APAC/incidents/$INCIDENT_ID" | jq '.vector_clock')
log_info "region-us vector clock: $VC_INITIAL"
log_info "region-eu vector clock: $EU_VC"
log_info "region-apac vector clock: $APAC_VC"

# ─── STEP 4: Simulate partition — update US WITHOUT notifying EU ─────────────
log_step 4 "SIMULATING PARTITION — updating incident in region-us (EU is partitioned)"
echo -e "  ${RED}🔌 Network partition: region-us cannot reach region-eu${NC}"

# Get current clock from US
US_CURRENT=$(curl -sf "$US/incidents/$INCIDENT_ID")
US_VC=$(echo "$US_CURRENT" | jq '.vector_clock')

US_UPDATE=$(curl -sf -X PUT "$US/incidents/$INCIDENT_ID" \
    -H "Content-Type: application/json" \
    -d "{
      \"status\": \"ACKNOWLEDGED\",
      \"assigned_team\": \"SRE-Team-US\",
      \"vector_clock\": $US_VC
    }")

US_VC_AFTER=$(echo "$US_UPDATE" | jq '.vector_clock')
log_info "region-us updated. New vector clock: $US_VC_AFTER"

# ─── STEP 5: Concurrent update in EU (partition is still active) ─────────────
log_step 5 "Concurrent update in region-eu (partition still active — EU has NOT seen US update)"

EU_CURRENT=$(curl -sf "$EU/incidents/$INCIDENT_ID")
EU_VC=$(echo "$EU_CURRENT" | jq '.vector_clock')

EU_UPDATE=$(curl -sf -X PUT "$EU/incidents/$INCIDENT_ID" \
    -H "Content-Type: application/json" \
    -d "{
      \"status\": \"CRITICAL\",
      \"assigned_team\": \"SRE-Team-EU\",
      \"vector_clock\": $EU_VC
    }")

EU_VC_AFTER=$(echo "$EU_UPDATE" | jq '.vector_clock')
log_info "region-eu updated concurrently. New vector clock: $EU_VC_AFTER"

log_warn "Two concurrent updates created:"
log_info "  US update: status=ACKNOWLEDGED, vc=$US_VC_AFTER"
log_info "  EU update: status=CRITICAL,     vc=$EU_VC_AFTER"

# ─── STEP 6: Remove partition — replicate US version TO EU ───────────────────
log_step 6 "REMOVING PARTITION — replicating region-us update to region-eu"
echo -e "  ${GREEN}🔌 Network restored: sending US version to EU's /internal/replicate${NC}"

# Refresh US state to get the updated version
US_LATEST=$(curl -sf "$US/incidents/$INCIDENT_ID")

REPLICATE_RESPONSE=$(curl -sf -X POST "$EU/internal/replicate" \
    -H "Content-Type: application/json" \
    -d "$US_LATEST")

log_info "Replication response from region-eu: $(echo $REPLICATE_RESPONSE | jq -r '.action')"

# ─── STEP 7: Verify conflict is detected in EU ───────────────────────────────
log_step 7 "Fetching incident from region-eu to verify conflict detection"
sleep 1

EU_FINAL=$(curl -sf "$EU/incidents/$INCIDENT_ID")
CONFLICT_FLAG=$(echo "$EU_FINAL" | jq '.version_conflict')
EU_FINAL_VC=$(echo "$EU_FINAL" | jq '.vector_clock')

log_info "region-eu final vector clock: $EU_FINAL_VC"

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
if [ "$CONFLICT_FLAG" = "true" ]; then
    echo -e "${GREEN}✅ SUCCESS: Conflict detected! version_conflict = true${NC}"
else
    echo -e "${RED}❌ UNEXPECTED: version_conflict = $CONFLICT_FLAG (expected true)${NC}"
fi
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Final incident state from region-eu:${NC}"
log_json "$EU_FINAL"

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}BONUS: Resolving conflict on region-eu${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"

RESOLVED=$(curl -sf -X POST "$EU/incidents/$INCIDENT_ID/resolve" \
    -H "Content-Type: application/json" \
    -d '{"status":"RESOLVED","assigned_team":"SRE-Managers"}')

log_info "Conflict resolved!"
log_json "$RESOLVED"

echo ""
echo -e "${GREEN}🎉 Partition simulation complete!${NC}"
echo ""
