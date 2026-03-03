from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1029_hogflow_draft_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="experiment",
            name="phases",
            field=models.JSONField(blank=True, default=list, null=True),
        ),
    ]
