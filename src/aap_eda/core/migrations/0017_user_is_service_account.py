# Generated by Django 4.2.7 on 2023-12-18 21:14

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_activationinstancelog_log_timestamp"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_service_account",
            field=models.BooleanField(default=False),
        ),
    ]