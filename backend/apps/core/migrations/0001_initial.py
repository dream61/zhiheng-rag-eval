# Django 5.0.14 自动生成的初始数据库迁移。

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Asset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('knowledge', '知识库'), ('dataset', '数据集')], max_length=20)),
                ('name', models.CharField(max_length=120)),
                ('product', models.CharField(max_length=120)),
                ('version', models.CharField(max_length=40)),
                ('content', models.JSONField(default=list)),
                ('settings', models.JSONField(default=dict)),
                ('published', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Experiment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('config', models.JSONField(default=dict)),
                ('snapshot', models.JSONField(default=dict)),
                ('status', models.CharField(default='pending', max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Result',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sample_id', models.CharField(max_length=80)),
                ('sample', models.JSONField()),
                ('status', models.CharField(default='pending', max_length=30)),
                ('trace', models.JSONField(default=dict)),
                ('scores', models.JSONField(default=dict)),
                ('error', models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('passed', models.BooleanField()),
                ('reason', models.TextField()),
                ('attribution', models.CharField(blank=True, max_length=80)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name='asset',
            constraint=models.UniqueConstraint(fields=('kind', 'product', 'name', 'version'), name='unique_asset_version'),
        ),
        migrations.AddField(
            model_name='experiment',
            name='created_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='experiment',
            name='dataset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='dataset_experiments', to='core.asset'),
        ),
        migrations.AddField(
            model_name='experiment',
            name='knowledge',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='knowledge_experiments', to='core.asset'),
        ),
        migrations.AddField(
            model_name='result',
            name='experiment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='results', to='core.experiment'),
        ),
        migrations.AddField(
            model_name='review',
            name='result',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reviews', to='core.result'),
        ),
        migrations.AddField(
            model_name='review',
            name='reviewer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name='result',
            constraint=models.UniqueConstraint(fields=('experiment', 'sample_id'), name='unique_experiment_sample'),
        ),
    ]
