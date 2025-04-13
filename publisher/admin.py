# /Users/junluo/Documents/wechat_publisher_web/publisher/admin.py
"""
Django admin configuration for the publisher app.

Registers models with the Django admin site for easy management and debugging.
"""
from django.contrib import admin
from .models import PublishingJob # Import your model

@admin.register(PublishingJob)
class PublishingJobAdmin(admin.ModelAdmin):
    """
    Admin configuration for the PublishingJob model.
    """
    list_display = ('task_id', 'status', 'get_title', 'created_at', 'updated_at', 'wechat_media_id')
    list_filter = ('status', 'created_at')
    search_fields = ('task_id', 'metadata__title', 'wechat_media_id', 'error_message') # Enable search
    readonly_fields = ('task_id', 'created_at', 'updated_at') # Fields not editable in admin

    fieldsets = (
        (None, {
            'fields': ('task_id', 'status', 'error_message')
        }),
        ('Input & Preview', {
            'fields': ('original_markdown_path', 'original_cover_image_path', 'preview_html_path')
        }),
        ('WeChat Data', {
            'fields': ('metadata', 'thumb_media_id', 'wechat_media_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',) # Make this section collapsible
        }),
    )

    @admin.display(description='Title')
    def get_title(self, obj):
        """Helper to display title from metadata JSON."""
        if isinstance(obj.metadata, dict):
            return obj.metadata.get('title', 'N/A')
        return 'N/A'

# Register other models here if you create more
# admin.site.register(YourOtherModel)