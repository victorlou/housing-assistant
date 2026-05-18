CREATE TABLE "ai_chatbot"."saved_searches" (
	"search_id" text PRIMARY KEY NOT NULL,
	"user_id" text NOT NULL,
	"name" text NOT NULL,
	"query_json" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "ai_chatbot"."alerts" (
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
ALTER TABLE "ai_chatbot"."alerts" ADD CONSTRAINT "alerts_search_id_saved_searches_search_id_fk" FOREIGN KEY ("search_id") REFERENCES "ai_chatbot"."saved_searches"("search_id") ON DELETE set null ON UPDATE no action;
