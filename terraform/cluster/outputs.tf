output "instance_id" {
  value = aws_instance.k3s.id
}

output "public_ip" {
  description = "Public IP used by the ingress (HTTP/HTTPS)"
  value       = aws_instance.k3s.public_ip
}

output "connect_command" {
  description = "Open a shell on the node without SSH"
  value       = "aws ssm start-session --target ${aws_instance.k3s.id}"
}
