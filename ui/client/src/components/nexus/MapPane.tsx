/**
 * MapPane - styled shell only.
 *
 * The real PostGIS map is milestone U4 (see docs/maptab_rebuild_spec.md).
 * This pane reserves the surface with the themed bordered canvas and a
 * faint coordinate grid, deliberately pulling in no map libraries.
 */
export function MapPane() {
  return (
    <div className="mappane-shell" data-testid="map-pane">
      <div className="mappane-canvas">
        <svg
          className="mappane-grid"
          aria-hidden="true"
          preserveAspectRatio="none"
        >
          <defs>
            <pattern
              id="nexus-map-grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M40 0H0V40"
                fill="none"
                stroke="var(--brass)"
                strokeOpacity="0.06"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#nexus-map-grid)" />
        </svg>
        <div className="mappane-placeholder">
          <span className="eyebrow brass-glow">[ CARTOGRAPHY ]</span>
          <h2 className="map-title">SURVEY PENDING</h2>
          <p className="map-sub">
            The atlas is being re-engraved. Zones, places, and routes return
            with the next survey.
          </p>
        </div>
      </div>
    </div>
  );
}
