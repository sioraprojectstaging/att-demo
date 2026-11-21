import os

from django.core.management.base import BaseCommand, CommandError
from api.models import User


class Command(BaseCommand):
    help = (
        'Creates the initial SUPER_ADMIN account. Credentials come from options '
        'or the SUPERADMIN_USERNAME / SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD '
        'environment variables; nothing is hardcoded.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--username', default=os.getenv('SUPERADMIN_USERNAME', 'superadmin'))
        parser.add_argument('--email', default=os.getenv('SUPERADMIN_EMAIL'))
        parser.add_argument('--password', default=os.getenv('SUPERADMIN_PASSWORD'))

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']

        if not email or not password:
            raise CommandError(
                'Provide --email and --password (or set SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD).'
            )

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'SUPER_ADMIN "{username}" already exists.'))
            return

        User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role='SUPER_ADMIN',
            first_name='Super',
            last_name='Admin',
            is_approved=True,
            is_staff=True,
            is_superuser=True
        )

        self.stdout.write(self.style.SUCCESS('SUPER_ADMIN created successfully!'))
        self.stdout.write(f'  Username: {username}')
        self.stdout.write(f'  Email: {email}')
