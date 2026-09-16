CREATE TABLE IF NOT EXISTS merchants (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL UNIQUE CHECK (id = merchant_id),
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS channels (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_channels_merchant ON channels(merchant_id);

CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_products_merchant_status ON products(merchant_id, (data->>'status'));

CREATE TABLE IF NOT EXISTS variants (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_variants_merchant_sku ON variants(merchant_id, (data->>'sku'));

CREATE TABLE IF NOT EXISTS product_drafts (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  sku TEXT,
  state TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (merchant_id, sku)
);
CREATE INDEX IF NOT EXISTS idx_product_drafts_merchant_state ON product_drafts(merchant_id, state);

CREATE TABLE IF NOT EXISTS media_assets (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_media_assets_merchant ON media_assets(merchant_id);

CREATE TABLE IF NOT EXISTS publications (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  product_draft_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  status TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_publications_merchant_status ON publications(merchant_id, status);
-- Phase 4.6: DB-enforced (not merely SELECT-before-INSERT) guard against two Publication rows for the
-- same draft+channel both being "in flight or done" at once - see postgres_store.py's Publication branch.
CREATE UNIQUE INDEX IF NOT EXISTS uq_publication_draft_channel ON publications(merchant_id, product_draft_id, channel_id) WHERE status IN ('approved', 'publishing', 'published');

CREATE TABLE IF NOT EXISTS publication_attempts (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  publication_id TEXT NOT NULL,
  connector_command_id TEXT NOT NULL,
  status TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_publication_attempts_pub ON publication_attempts(merchant_id, publication_id);

CREATE TABLE IF NOT EXISTS listing_verifications (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  publication_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_listing_verifications_outcome ON listing_verifications(merchant_id, outcome);

-- Stage 4: Durable merchant-scoped product identity decisions (SAME / DIFFERENT)
CREATE TABLE IF NOT EXISTS identity_decisions (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_identity_decisions_merchant ON identity_decisions(merchant_id);

CREATE TABLE IF NOT EXISTS merchant_configurations (
  merchant_id TEXT PRIMARY KEY REFERENCES merchants(id) ON DELETE CASCADE,
  config JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credential_references (
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  ref TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'env',
  locator TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (merchant_id, ref)
);

-- Step P0.1: production credential storage - see packages/domain_contract/credentials.py
-- (DurableEncryptedCredentialProvider). Contains NO credentials and NO encryption key - `ciphertext`/
-- `nonce` are meaningless without the externally-supplied master key for `key_version`. `id` is a
-- separate surrogate key (not merchant_id/ref) so a locator can identify one exact row even across a
-- rotation; `(merchant_id, ref)` stays UNIQUE so ON CONFLICT can implement safe replace/rotate in one
-- statement. `revoked_at IS NOT NULL` means the credential must never be returned by resolve() again -
-- rows are never hard-deleted, preserving evidence, matching this codebase's append-only audit
-- philosophy elsewhere.
CREATE TABLE IF NOT EXISTS encrypted_credentials (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  ref TEXT NOT NULL,
  ciphertext BYTEA NOT NULL,
  nonce BYTEA NOT NULL,
  key_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ,
  UNIQUE (merchant_id, ref)
);

CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_customers_merchant_email ON customers(merchant_id, (data->>'email'));

CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  event_sequence BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_orders_merchant ON orders(merchant_id);
CREATE INDEX IF NOT EXISTS idx_orders_merchant_number ON orders(merchant_id, (data->>'order_number'));

CREATE TABLE IF NOT EXISTS order_lines (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_order_lines_order ON order_lines(merchant_id, order_id);

CREATE TABLE IF NOT EXISTS payments (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(merchant_id, (data->>'order_id'));

CREATE TABLE IF NOT EXISTS payment_observations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_observations_order ON payment_observations(merchant_id, (data->>'order_id'));
-- RUNTIME-DEBT: this file is a single ever-growing migration (see docs/architecture/phase3-finance-operations.md
-- "Tracked debt" section); a real deployment needs incremental/versioned migrations instead of editing this file.
-- Final-authority uniqueness for payment observation idempotency (Phase 3 hardening): a partial unique index so
-- multiple observations with no external_payment_id (unknown-reference cases) remain permitted, but any repeated
-- delivery of the same (merchant, provider, external_payment_id) - e.g. a gateway webhook retry - can only ever
-- persist as a single row, enforced by Postgres itself rather than application-level checks.
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_observation_external
  ON payment_observations(merchant_id, (data->>'provider'), (data->>'external_payment_id'))
  WHERE (data->>'external_payment_id') IS NOT NULL;

CREATE TABLE IF NOT EXISTS settlement_batches (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_settlement_batch_external ON settlement_batches(merchant_id, (data->>'provider'), (data->>'external_batch_id'));

CREATE TABLE IF NOT EXISTS settlement_entries (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_settlement_entries_order ON settlement_entries(merchant_id, (data->>'order_id'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_settlement_entry_external ON settlement_entries(merchant_id, (data->>'provider'), (data->>'external_entry_id'));

CREATE TABLE IF NOT EXISTS finance_reconciliations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_finance_reconciliations_result ON finance_reconciliations(merchant_id, (data->>'result'));
CREATE INDEX IF NOT EXISTS idx_finance_reconciliations_object ON finance_reconciliations(merchant_id, (data->>'object_type'), (data->>'object_id'));

CREATE TABLE IF NOT EXISTS inventory (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inventory_merchant_sku ON inventory(merchant_id, (data->>'sku'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_merchant_sku_location ON inventory(merchant_id, (data->>'sku'), (data->>'location_ref'));

-- 2026-09 reservation-lifecycle fix: the reservation OWNERSHIP ledger - see
-- packages/domain_contract/models.py InventoryReservation docstring for why ConnectorCommand history
-- alone was proven insufficient. uq_inventory_reservations_idempotency makes duplicate reservation
-- creation DB-impossible, not just app-checked (mirrors uq_purchase_order_idempotency below - same
-- final-authority-idempotency pattern, same reason).
CREATE TABLE IF NOT EXISTS inventory_reservations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inventory_reservations_source ON inventory_reservations(merchant_id, (data->>'source_type'), (data->>'source_id'));
CREATE INDEX IF NOT EXISTS idx_inventory_reservations_sku_location ON inventory_reservations(merchant_id, (data->>'sku'), (data->>'location_ref'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_reservations_idempotency ON inventory_reservations(merchant_id, (data->>'idempotency_key'));

CREATE TABLE IF NOT EXISTS fulfilments (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fulfilments_order ON fulfilments(merchant_id, (data->>'order_id'));

CREATE TABLE IF NOT EXISTS shipments (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shipments_order ON shipments(merchant_id, (data->>'order_id'));
CREATE INDEX IF NOT EXISTS idx_shipments_tracking ON shipments(merchant_id, (data->>'tracking_number'));

CREATE TABLE IF NOT EXISTS tracking_events (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tracking_events_shipment ON tracking_events(merchant_id, (data->>'shipment_id'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_tracking_event_sequence ON tracking_events(merchant_id, (data->>'shipment_id'), (data->>'external_sequence'), (data->>'status'));

CREATE TABLE IF NOT EXISTS returns (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_returns_order ON returns(merchant_id, (data->>'order_id'));

CREATE TABLE IF NOT EXISTS exchanges (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_exchanges_order ON exchanges(merchant_id, (data->>'order_id'));

CREATE TABLE IF NOT EXISTS refunds (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refunds_order ON refunds(merchant_id, (data->>'order_id'));
-- Step 7B: final-authority idempotency for the Return -> Refund automatic trigger - at most one Refund
-- per (merchant_id, return_id), mirroring uq_purchase_order_idempotency's exact partial-unique-index
-- pattern. This, not any application-level pre-check, is what makes two genuinely concurrent
-- observations of the same refund-eligible Return converge on exactly one Refund row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_refund_return_id
  ON refunds(merchant_id, (data->>'return_id'))
  WHERE (data->>'return_id') IS NOT NULL;

CREATE TABLE IF NOT EXISTS cancellations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cancellations_order ON cancellations(merchant_id, (data->>'order_id'));

CREATE TABLE IF NOT EXISTS inventory_observations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  order_id TEXT,
  sku TEXT NOT NULL,
  status TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inventory_obs_order ON inventory_observations(merchant_id, order_id);

CREATE TABLE IF NOT EXISTS fulfilment_observations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  order_id TEXT NOT NULL,
  status TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fulfilment_obs_order ON fulfilment_observations(merchant_id, order_id);

CREATE TABLE IF NOT EXISTS shipment_observations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  order_id TEXT NOT NULL,
  status TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shipment_obs_order ON shipment_observations(merchant_id, order_id);

CREATE TABLE IF NOT EXISTS support_conversations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_support_conversations_merchant ON support_conversations(merchant_id);

CREATE TABLE IF NOT EXISTS support_intents (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_support_intents_conversation ON support_intents(merchant_id, conversation_id);

CREATE TABLE IF NOT EXISTS customer_support_actions (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL,
  handling_mode TEXT NOT NULL,
  status TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_support_actions_mode ON customer_support_actions(merchant_id, handling_mode, status);

CREATE TABLE IF NOT EXISTS external_id_mappings (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  sanocea_entity_type TEXT NOT NULL,
  sanocea_id TEXT NOT NULL,
  external_system TEXT NOT NULL,
  external_entity_type TEXT NOT NULL,
  external_id TEXT NOT NULL,
  channel_id TEXT,
  first_seen_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL,
  UNIQUE (merchant_id, external_system, external_entity_type, external_id)
);
CREATE INDEX IF NOT EXISTS idx_external_mapping_sanocea ON external_id_mappings(merchant_id, sanocea_entity_type, sanocea_id);

CREATE TABLE IF NOT EXISTS raw_external_events (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  payload JSONB NOT NULL,
  headers JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL,
  checksum TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_events_merchant_source ON raw_external_events(merchant_id, source, received_at DESC);

CREATE TABLE IF NOT EXISTS idempotency_records (
  scope TEXT NOT NULL,
  key TEXT NOT NULL,
  result JSONB,
  status TEXT NOT NULL DEFAULT 'reserved',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  PRIMARY KEY (scope, key)
);

CREATE TABLE IF NOT EXISTS connector_commands (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  connector TEXT NOT NULL,
  action TEXT NOT NULL,
  object_type TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (merchant_id, connector, action, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_connector_commands_status ON connector_commands(merchant_id, status);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_approvals_merchant_status ON approvals(merchant_id, (data->>'status'));

CREATE TABLE IF NOT EXISTS exceptions (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_exceptions_merchant_status ON exceptions(merchant_id, (data->>'status'));

CREATE TABLE IF NOT EXISTS workflow_executions (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  workflow_type TEXT NOT NULL,
  business_key TEXT NOT NULL,
  temporal_workflow_id TEXT NOT NULL,
  temporal_run_id TEXT,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (merchant_id, workflow_type, business_key)
);
CREATE INDEX IF NOT EXISTS idx_workflows_merchant_status ON workflow_executions(merchant_id, (data->>'status'));

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  actor TEXT NOT NULL,
  source TEXT NOT NULL,
  action TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT,
  timestamp TIMESTAMPTZ NOT NULL,
  workflow_id TEXT,
  evidence_ref TEXT,
  requested_mutation JSONB,
  result TEXT NOT NULL,
  external_ref JSONB,
  error TEXT,
  correlation_id TEXT
);
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS correlation_id TEXT;
CREATE INDEX IF NOT EXISTS idx_audit_merchant_time ON audit_events(merchant_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_events(merchant_id, object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_audit_correlation ON audit_events(correlation_id) WHERE correlation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS reconciliation_results (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  scope JSONB NOT NULL,
  canonical_ref JSONB,
  external_ref JSONB,
  result TEXT NOT NULL,
  exception_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reconciliation_merchant_time ON reconciliation_results(merchant_id, created_at DESC);

CREATE OR REPLACE FUNCTION prevent_audit_update_delete() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_events;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_update_delete();

-- Phase 4: Inventory Planning, Procurement & Supplier Operations.
-- RUNTIME-DEBT (tracked, see docs/architecture/phase3-finance-operations.md): still a single
-- ever-growing migration file rather than incremental/versioned migrations.

CREATE TABLE IF NOT EXISTS suppliers (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_suppliers_merchant_status ON suppliers(merchant_id, (data->>'status'));

CREATE TABLE IF NOT EXISTS supplier_skus (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_supplier_skus_sku ON supplier_skus(merchant_id, (data->>'sku'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_sku_offer ON supplier_skus(merchant_id, (data->>'supplier_id'), (data->>'sku'));

CREATE TABLE IF NOT EXISTS replenishment_recommendations (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_replenishment_sku ON replenishment_recommendations(merchant_id, (data->>'sku'));

CREATE TABLE IF NOT EXISTS purchase_orders (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier ON purchase_orders(merchant_id, (data->>'supplier_id'));
CREATE INDEX IF NOT EXISTS idx_purchase_orders_status ON purchase_orders(merchant_id, (data->>'status'));
-- Final-authority idempotency: a caller retrying create_purchase_order() with the same idempotency_key
-- (e.g. derived from a ReplenishmentRecommendation id) must never create a second DRAFT PO.
CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_order_idempotency
  ON purchase_orders(merchant_id, (data->>'idempotency_key'))
  WHERE (data->>'idempotency_key') IS NOT NULL;

CREATE TABLE IF NOT EXISTS purchase_order_lines (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_po_lines_po ON purchase_order_lines(merchant_id, (data->>'purchase_order_id'));

CREATE TABLE IF NOT EXISTS supplier_acknowledgements (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_acks_po ON supplier_acknowledgements(merchant_id, (data->>'purchase_order_id'));
-- Final authority against duplicate/stale/out-of-order acknowledgement events: the same external
-- acknowledgement reference for the same PO can only ever persist as one row.
CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_ack_external
  ON supplier_acknowledgements(merchant_id, (data->>'purchase_order_id'), (data->>'external_ref'))
  WHERE (data->>'external_ref') IS NOT NULL;

CREATE TABLE IF NOT EXISTS inbound_shipments (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inbound_shipments_po ON inbound_shipments(merchant_id, (data->>'purchase_order_id'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_inbound_shipment_external
  ON inbound_shipments(merchant_id, (data->>'supplier_id'), (data->>'external_shipment_ref'))
  WHERE (data->>'external_shipment_ref') IS NOT NULL;

CREATE TABLE IF NOT EXISTS inbound_shipment_lines (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inbound_shipment_lines_shipment ON inbound_shipment_lines(merchant_id, (data->>'inbound_shipment_id'));

CREATE TABLE IF NOT EXISTS goods_receipts (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_goods_receipts_po ON goods_receipts(merchant_id, (data->>'purchase_order_id'));
CREATE UNIQUE INDEX IF NOT EXISTS uq_goods_receipt_external
  ON goods_receipts(merchant_id, (data->>'external_receipt_ref'))
  WHERE (data->>'external_receipt_ref') IS NOT NULL;

CREATE TABLE IF NOT EXISTS goods_receipt_lines (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_goods_receipt_lines_receipt ON goods_receipt_lines(merchant_id, (data->>'goods_receipt_id'));

-- Phase 4.5: Commerce OS Integration & Operationalization.
-- Smallest reusable auth foundation - not a general IAM product. merchant_id is nullable because a
-- 'service' key (the background recovery worker, internal jobs) is not scoped to one merchant; every
-- 'operator' key IS scoped to exactly one merchant and that scope is the tenant authorization boundary
-- (never a client-supplied merchant_id path parameter alone).
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  merchant_id TEXT REFERENCES merchants(id) ON DELETE CASCADE,
  key_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  label TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_merchant ON api_keys(merchant_id, role);
