# For now we use local state. The state file is committed to .gitignore so it
# stays on each developer's machine. Coordinate via Slack / a shared lock file
# when more than one person needs to apply at the same time.
#
# To migrate to remote state on S3 later:
#   1. Create an S3 bucket (and optional DynamoDB table for locking).
#   2. Uncomment the block below and fill in the values.
#   3. Run `terraform init -migrate-state`.
#
# terraform {
#   backend "s3" {
#     bucket         = "housing-assistant-tfstate"
#     key            = "envs/dev/terraform.tfstate"
#     region         = "us-west-2"
#     dynamodb_table = "housing-assistant-tflock"
#     encrypt        = true
#   }
# }
