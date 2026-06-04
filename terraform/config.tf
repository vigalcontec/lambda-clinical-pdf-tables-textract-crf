# =============================================================================
# Configuration - Update these values for your project
# =============================================================================

locals {
  # ─────────────────────────────────────────────────────────────────────────────
  # Project Configuration (UPDATE THESE)
  # ─────────────────────────────────────────────────────────────────────────────
  function_name = "lambda-clinical-pdf-tables-textract-crf" # Lambda function name (without env suffix)
  project_name  = "clinical-rag-foundry"                    # Project name for tagging
  company_name  = "vigalcontec"                             # Company name for resource naming

  # ─────────────────────────────────────────────────────────────────────────────
  # AWS Configuration
  # ─────────────────────────────────────────────────────────────────────────────
  aws_region = "eu-west-1"

  # ─────────────────────────────────────────────────────────────────────────────
  # Lambda Configuration
  # ─────────────────────────────────────────────────────────────────────────────
  timeout            = 300 # Lambda timeout in seconds (5 min for Textract)
  memory_size        = 512 # Lambda memory in MB (for PDF processing)
  log_level          = "INFO"
  log_retention_days = 30

  # ─────────────────────────────────────────────────────────────────────────────
  # SSM Export Name (used by Step Function to find this Lambda)
  # ─────────────────────────────────────────────────────────────────────────────
  ssm_export_name = "clinical-pdf-textract-crf"

  # ─────────────────────────────────────────────────────────────────────────────
  # Computed Values (DO NOT MODIFY)
  # ─────────────────────────────────────────────────────────────────────────────
  account_id   = data.aws_caller_identity.current.account_id
  full_name    = "${local.function_name}-${var.environment}"
  state_bucket = "tfstate-${local.company_name}-${var.environment}-${local.account_id}"

  # Common tags
  common_tags = {
    Project     = local.project_name
    Function    = local.function_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
