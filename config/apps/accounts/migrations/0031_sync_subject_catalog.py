"""Synchronize legacy Subject rows with the catalog introduced in 0029."""

from django.db import migrations


_TEMPORARY_NUMBER_OFFSET = 10_000


def _target_number_for_legacy_number(number):
    """Return the 0029 catalog number for a pre-0029 subject [number]."""
    if number <= 17:
        return number
    if number <= 30:
        return number + 1
    if number <= 32:
        return number + 2
    if number <= 50:
        return number + 3
    return number + 5


def _merge_subject_relations(source, target):
    """Move every many-to-many relation from duplicate [source] to [target]."""
    for relation in source._meta.related_objects:
        if not relation.many_to_many:
            continue

        through = relation.through
        subject_field = next(
            field
            for field in through._meta.fields
            if field.remote_field and field.remote_field.model == source.__class__
        )
        owner_field = next(
            field
            for field in through._meta.fields
            if field is not subject_field and field.remote_field
        )

        source_links = through.objects.filter(**{subject_field.name: source.pk})
        for link in source_links.iterator():
            owner_id = getattr(link, owner_field.attname)
            target_filter = {
                subject_field.name: target.pk,
                owner_field.attname: owner_id,
            }
            if through.objects.filter(**target_filter).exists():
                link.delete()
            else:
                setattr(link, subject_field.attname, target.pk)
                link.save(update_fields=[subject_field.name])


def sync_subject_catalog(apps, schema_editor):
    """Re-number legacy subjects while preserving every existing relationship."""
    Subject = apps.get_model("accounts", "Subject")
    target_subjects = tuple(Subject._meta.get_field("number").choices)
    target_names = dict(target_subjects)
    target_numbers = tuple(target_names)

    existing_subjects = Subject.objects.filter(number__in=target_numbers)
    if not existing_subjects.exists():
        Subject.objects.bulk_create(
            [Subject(number=number, name=name) for number, name in target_subjects],
        )
        return

    is_current_catalog = all(
        target_names[number] == name
        for number, name in existing_subjects.values_list("number", "name")
    )
    if is_current_catalog:
        for number, name in target_subjects:
            Subject.objects.update_or_create(number=number, defaults={"name": name})
        return

    legacy_subjects = list(
        Subject.objects.filter(number__gte=1, number__lte=279).order_by("number"),
    )
    legacy_by_number = {subject.number: subject for subject in legacy_subjects}

    for subject in legacy_subjects:
        subject.number += _TEMPORARY_NUMBER_OFFSET
        subject.save(update_fields=["number"])

    for legacy_number in range(1, 275):
        subject = legacy_by_number.get(legacy_number)
        if subject is None:
            continue
        target_number = _target_number_for_legacy_number(legacy_number)
        subject.number = target_number
        subject.name = target_names[target_number]
        subject.save(update_fields=["number", "name"])

    for legacy_number in range(275, 280):
        duplicate = legacy_by_number.get(legacy_number)
        if duplicate is None:
            continue
        target = Subject.objects.filter(number=legacy_number).first()
        if target is None:
            duplicate.number = legacy_number
            duplicate.name = target_names[legacy_number]
            duplicate.save(update_fields=["number", "name"])
        else:
            _merge_subject_relations(duplicate, target)
            duplicate.delete()

    for number, name in target_subjects:
        Subject.objects.update_or_create(number=number, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0030_instructor_is_official_creator"),
        ("lecture", "0010_lecture_sample_preview"),
        ("tutoring", "0026_commissioninvoice_promotion_benefit"),
    ]

    operations = [
        migrations.RunPython(sync_subject_catalog, migrations.RunPython.noop),
    ]
