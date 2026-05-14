CREATE TABLE "alerts" (
	"alert_id" text PRIMARY KEY NOT NULL,
	"user_id" text NOT NULL,
	"search_id" text,
	"threshold_json" jsonb,
	"channel" text NOT NULL,
	"channel_target" text NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"last_fired_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "conversation_turns" (
	"turn_id" text PRIMARY KEY NOT NULL,
	"user_id" text NOT NULL,
	"session_id" text NOT NULL,
	"role" text NOT NULL,
	"content" text NOT NULL,
	"tool_calls" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "users" (
	"user_id" text PRIMARY KEY NOT NULL,
	"email" text NOT NULL,
	"display_name" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "users_email_unique" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE "saved_searches" (
	"search_id" text PRIMARY KEY NOT NULL,
	"user_id" text NOT NULL,
	"name" text NOT NULL,
	"query_json" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "user_constraints" (
	"constraint_id" text PRIMARY KEY NOT NULL,
	"user_id" text NOT NULL,
	"name" text,
	"is_default" boolean DEFAULT false NOT NULL,
	"budget_weekly_max" integer,
	"household_size" smallint,
	"has_pets" boolean,
	"work_location" text,
	"preferred_modes" text[],
	"max_commute_mins" smallint,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "alerts" ADD CONSTRAINT "alerts_user_id_users_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "alerts" ADD CONSTRAINT "alerts_search_id_saved_searches_search_id_fk" FOREIGN KEY ("search_id") REFERENCES "public"."saved_searches"("search_id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "conversation_turns" ADD CONSTRAINT "conversation_turns_user_id_users_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "saved_searches" ADD CONSTRAINT "saved_searches_user_id_users_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "user_constraints" ADD CONSTRAINT "user_constraints_user_id_users_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("user_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "idx_conv_turns_user_session" ON "conversation_turns" USING btree ("user_id","session_id","created_at");--> statement-breakpoint
CREATE INDEX "idx_user_constraints_user" ON "user_constraints" USING btree ("user_id");