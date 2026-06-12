resource "aws_efs_file_system" "assets" {
  creation_token = "${local.name_prefix}-assets"
  encrypted      = true

  tags = {
    Name = "${local.name_prefix}-assets"
  }
}

resource "aws_efs_mount_target" "assets" {
  count = local.private_subnet_count

  file_system_id  = aws_efs_file_system.assets.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

resource "aws_efs_access_point" "assets" {
  file_system_id = aws_efs_file_system.assets.id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/assets"

    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "0775"
    }
  }

  tags = {
    Name = "${local.name_prefix}-assets-ap"
  }
}
