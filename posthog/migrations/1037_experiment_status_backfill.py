from django.db import migrations


def backfill_experiment_status(apps, schema_editor):
    Experiment = apps.get_model("posthog", "Experiment")
    Experiment.objects.filter(start_date__isnull=True).update(status="draft")
    Experiment.objects.filter(start_date__isnull=False, end_date__isnull=True).update(status="running")
    Experiment.objects.filter(end_date__isnull=False).update(status="stopped")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("posthog", "1036_experiment_status"),
    ]

    operations = [
        migrations.RunPython(backfill_experiment_status, reverse_code=migrations.RunPython.noop),
    ]
