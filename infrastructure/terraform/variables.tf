variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "dev | prod"
  type        = string
  default     = "prod"
}

variable "app_name" {
  description = "Prefix for all resource names"
  type        = string
  default     = "kakapo"
}

variable "db_password" {
  description = "RDS master password (use a strong random string)"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "gemini_api_key" {
  description = "Google Gemini API key"
  type        = string
  sensitive   = true
}

variable "initial_admin_key" {
  description = "Raw value for the first admin API key seeded on startup"
  type        = string
  sensitive   = true
}

variable "initial_tenant_name" {
  description = "Display name for the default tenant"
  type        = string
  default     = "Default"
}

variable "api_cpu" {
  description = "ECS task CPU units"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "ECS task memory (MB)"
  type        = number
  default     = 1024
}

variable "api_min_capacity" {
  type    = number
  default = 1
}

variable "api_max_capacity" {
  type    = number
  default = 10
}
