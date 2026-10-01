import React from 'react'

export default function SearchAppearanceProgressionCard({progressionData}) {
  if (!progressionData || progressionData.length === 0) return null

  return (
    <div className="search-appearance-card">
      <div className="sa-card-header">
        <div className="sa-title-row">
          <span className="sa-sparkle">🔍</span>
          <h3 className="sa-title">Google Search Appearance: The 3-State Truth</h3>
          <span className="sa-badge-progression">Schema Declared ➔ Eligible ➔ Surfaced</span>
        </div>
        <p className="sa-subtitle">
          <strong>Crucial Commercial Distinction:</strong> Declaring JSON-LD on a webpage does NOT mean Google is showing rich results.
          SANOCEA monitors the complete three-tier lifecycle to protect merchant rich snippet eligibility.
        </p>
      </div>

      <div className="sa-progression-grid">
        {progressionData.map((item, idx) => (
          <div key={idx} className={`sa-entity-row ${item.state.toLowerCase()}`}>
            <div className="sa-entity-header">
              <div className="sa-entity-title">{item.entityName}</div>
              <span className={`sa-state-pill ${item.state.toLowerCase()}`}>
                {item.state.replace(/_/g, ' ')}
              </span>
            </div>

            <div className="sa-three-stages">
              {/* Stage 1: Schema Declared */}
              <div className={`sa-stage-step ${item.schemaDeclared.status ? 'active' : 'failed'}`}>
                <div className="sa-step-indicator">
                  <span className="indicator-icon">{item.schemaDeclared.status ? '✓' : '✗'}</span>
                  <span className="indicator-label">1. Schema Declared</span>
                </div>
                <div className="sa-step-detail">{item.schemaDeclared.detail}</div>
              </div>

              <div className="sa-step-arrow">➔</div>

              {/* Stage 2: Google Eligible */}
              <div className={`sa-stage-step ${item.googleEligible.status ? 'active' : 'failed'}`}>
                <div className="sa-step-indicator">
                  <span className="indicator-icon">{item.googleEligible.status ? '✓' : '✗'}</span>
                  <span className="indicator-label">2. Google Eligible</span>
                </div>
                <div className="sa-step-detail">{item.googleEligible.detail}</div>
              </div>

              <div className="sa-step-arrow">➔</div>

              {/* Stage 3: Actually Surfaced */}
              <div className={`sa-stage-step ${item.actuallySurfaced.status ? 'active' : 'unsurfaced'}`}>
                <div className="sa-step-indicator">
                  <span className="indicator-icon">{item.actuallySurfaced.status ? '★' : '○'}</span>
                  <span className="indicator-label">3. Actually Surfaced</span>
                </div>
                <div className="sa-step-detail">{item.actuallySurfaced.detail}</div>
              </div>
            </div>

            <div className="sa-verdict-banner">
              <strong>SANOCEA Diagnosis:</strong> {item.verdictText}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
