import type { InferSelectModel } from 'drizzle-orm';
import { boolean, integer, jsonb, pgSchema, text, timestamp, unique } from 'drizzle-orm/pg-core';

// Housing domain tables — ai_chatbot schema (same as chat UI tables)
const housingSchema = pgSchema('ai_chatbot');
const createTable = housingSchema.table;

export const savedSearches = createTable('saved_searches', {
  search_id: text('search_id').primaryKey().notNull(),
  user_id: text('user_id').notNull(),
  name: text('name').notNull(),
  query_json: jsonb('query_json').notNull(),
  created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
});

export type SavedSearch = InferSelectModel<typeof savedSearches>;

export const alerts = createTable('alerts', {
  alert_id: text('alert_id').primaryKey().notNull(),
  user_id: text('user_id').notNull(),
  search_id: text('search_id').references(() => savedSearches.search_id, {
    onDelete: 'set null',
  }),
  threshold_json: jsonb('threshold_json'),
  channel: text('channel', { enum: ['email', 'webhook'] }).notNull(),
  channel_target: text('channel_target').notNull(),
  is_active: boolean('is_active').notNull().default(true),
  last_fired_at: timestamp('last_fired_at', { withTimezone: true }),
  created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
});

export type Alert = InferSelectModel<typeof alerts>;

export const suburbSaves = createTable(
  'suburb_saves',
  {
    id: text('id').primaryKey().notNull(),
    user_id: text('user_id').notNull(),
    suburb_name: text('suburb_name').notNull(),
    median_rent_weekly: integer('median_rent_weekly').notNull(),
    commute_minutes: integer('commute_minutes').notNull(),
    commute_mode: text('commute_mode').notNull(),
    hazard_risk: text('hazard_risk').notNull(),
    affordability_band: text('affordability_band').notNull(),
    saved_at: timestamp('saved_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    user_suburb_unique: unique().on(table.user_id, table.suburb_name),
  }),
);

export type SuburbSave = InferSelectModel<typeof suburbSaves>;
