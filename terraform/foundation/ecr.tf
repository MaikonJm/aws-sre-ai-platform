resource "aws_ecr_repository" "service" {
  for_each = var.ecr_repositories

  name                 = "${var.project}/${each.key}"
  image_tag_mutability = "IMMUTABLE" # a tag always points to the same build
  force_delete         = true        # lab: allow destroy with images inside

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "service" {
  for_each = aws_ecr_repository.service

  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
