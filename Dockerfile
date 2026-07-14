FROM odoo:19.0

USER root
# Install external python dependencies for custom modules
RUN pip3 install --no-cache-dir linkpreview --break-system-packages

USER odoo
