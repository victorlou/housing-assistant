import type { InferSelectModel } from 'drizzle-orm';
import {
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  smallint,
  text,
  timestamp,
} from 'drizzle-orm/pg-core';

// Housing domain tables — public schema (NOT ai_chatbot schema)
// DDL source of truth migrated from terraform/modules/lakebase_migration/sql/schema.sql

export const housingUser = pgTable('users', {
  user_id: text('user_id').primaryKey().notNull(),
  email: text('email').unique().notNull(),
  display_name: text('display_name'),
  created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updated_at: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
});

export type HousingUser = InferSelectModel<typeof housingUser>;

export const userConstraints = pgTable(
  'user_constraints',
  {
    constraint_id: text('constraint_id')
      .primaryKey()
      .notNull()
      .$defaultFn(() => crypto.randomUUID()),
    user_id: text('user_id')
      .notNull()
      .references(() => housingUser.user_id, { onDelete: 'cascade' }),
    name: text('name'),
    is_default: boolean('is_default').notNull().default(false),
    budget_weekly_max: integer('budget_weekly_max'),
    household_size: smallint('household_size'),
    has_pets: boolean('has_pets'),
    work_location: text('work_location'),
    preferred_modes: text('preferred_modes').array(),
    max_commute_mins: smallint('max_commute_mins'),
    updated_at: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [index('idx_user_constraints_user').on(table.user_id)],
);

export type UserConstraints = InferSelectModel<typeof userConstraints>;

export const savedSearches = pgTable('saved_searches', {
  search_id: text('search_id')
    .primaryKey()
    .notNull()
    .$defaultFn(() => crypto.randomUUID()),
  user_id: text('user_id')
    .notNull()
    .references(() => housingUser.user_id, { onDelete: 'cascade' }),
  name: text('name').notNull(),
  query_json: jsonb('query_json').notNull(),
  created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
});

export type SavedSearch = InferSelectModel<typeof savedSearches>;

export const alerts = pgTable('alerts', {
  alert_id: text('alert_id')
    .primaryKey()
    .notNull()
    .$defaultFn(() => crypto.randomUUID()),
  user_id: text('user_id')
    .notNull()
    .references(() => housingUser.user_id, { onDelete: 'cascade' }),
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

export const conversationTurns = pgTable(
  'conversation_turns',
  {
    turn_id: text('turn_id')
      .primaryKey()
      .notNull()
      .$defaultFn(() => crypto.randomUUID()),
    user_id: text('user_id')
      .notNull()
      .references(() => housingUser.user_id, { onDelete: 'cascade' }),
    session_id: text('session_id').notNull(),
    role: text('role', { enum: ['user', 'assistant', 'tool'] }).notNull(),
    content: text('content').notNull(),
    tool_calls: jsonb('tool_calls'),
    created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    index('idx_conv_turns_user_session').on(
      table.user_id,
      table.session_id,
      table.created_at,
    ),
  ],
);

export type ConversationTurn = InferSelectModel<typeof conversationTurns>;
