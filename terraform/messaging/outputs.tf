output "orders_queue_name" {
  value = aws_sqs_queue.orders.name
}

output "orders_queue_arn" {
  value = aws_sqs_queue.orders.arn
}

output "orders_dlq_arn" {
  value = aws_sqs_queue.orders_dlq.arn
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
