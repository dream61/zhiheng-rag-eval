# 数据库迁移：审核、索引、执行尝试、租约与回归来源。

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='result',
            name='lease_token',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='result',
            name='lease_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='result',
            name='scoring_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='result',
            name='scoring_status',
            field=models.CharField(default='pending', max_length=30),
        ),
        migrations.CreateModel(
            name='ChatRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.TextField()),
                ('config', models.JSONField()),
                ('trace', models.JSONField(default=dict)),
                ('error', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('knowledge', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='core.asset')),
            ],
        ),
        migrations.CreateModel(
            name='ExecutionAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phase', models.CharField(max_length=20)),
                ('status', models.CharField(default='running', max_length=20)),
                ('error_type', models.CharField(blank=True, max_length=100)),
                ('output', models.JSONField(default=dict)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(null=True)),
                ('result', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='attempts', to='core.result')),
            ],
        ),
        migrations.CreateModel(
            name='IndexJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fingerprint', models.CharField(max_length=64)),
                ('status', models.CharField(default='pending', max_length=20)),
                ('backend', models.CharField(max_length=20)),
                ('snapshot', models.JSONField(default=dict)),
                ('collection', models.CharField(blank=True, max_length=100)),
                ('error', models.CharField(blank=True, max_length=100)),
                ('lease_until', models.DateTimeField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='index_jobs', to='core.asset')),
            ],
        ),
        migrations.CreateModel(
            name='RegressionMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sample_id', models.CharField(max_length=80)),
                ('reason', models.TextField()),
                ('expected_fix', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='regression_memberships', to='core.asset')),
                ('source_result', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='core.result')),
            ],
        ),
        migrations.CreateModel(
            name='SampleApproval',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sample_id', models.CharField(max_length=80)),
                ('content_hash', models.CharField(max_length=64)),
                ('approved', models.BooleanField()),
                ('reason', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='approvals', to='core.asset')),
                ('reviewer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='regressionmembership',
            constraint=models.UniqueConstraint(fields=('dataset', 'source_result'), name='unique_regression_source'),
        ),
    ]
