CREATE TABLE "ai_chatbot"."suburb_saves" (
	"id" text PRIMARY KEY NOT NULL,
	"user_id" text NOT NULL,
	"suburb_name" text NOT NULL,
	"median_rent_weekly" integer NOT NULL,
	"commute_minutes" integer NOT NULL,
	"commute_mode" text NOT NULL,
	"hazard_risk" text NOT NULL,
	"affordability_band" text NOT NULL,
	"saved_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "suburb_saves_user_id_suburb_name_unique" UNIQUE("user_id","suburb_name")
);
--> statement-breakpoint
