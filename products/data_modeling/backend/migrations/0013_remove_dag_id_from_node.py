from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("data_modeling", "0012_remove_node_constraints"),
    ]
    operations = [
        migrations.RemoveField(
            model_name="node",
            name="dag_id",
        ),
    ]
