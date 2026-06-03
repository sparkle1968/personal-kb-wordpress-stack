# 媒体处理流程

上传家庭照片和视频前，先在 Debian VM 上处理一遍：

```bash
cd /opt/home-wordpress
./scripts/prepare-media.sh /path/to/photos-or-videos
```

输出目录：

```text
prepared-media/
```

处理规则：

- 图片：自动旋转、移除元数据、输出 JPEG。
- 视频：移除元数据、压缩成 1080p H.264/AAC MP4。
- 视频封面：自动生成 `*-cover.jpg`。

发布时可以把处理后的图片作为 `--featured-media` 或 `--media` 传给 `publish-draft.py`。

示例：

```bash
python3 scripts/publish-draft.py \
  --site family \
  --title "五月家庭聚会" \
  --content-file examples/family-post.html \
  --featured-media prepared-media/party-cover.jpg \
  --media prepared-media/party.mp4 \
  --category "聚会"
```

