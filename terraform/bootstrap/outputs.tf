output "state_bucket" {
  description = "Bucket to use in the backend block of the other stacks"
  value       = aws_s3_bucket.tfstate.bucket
}

output "region" {
  value = var.region
}
