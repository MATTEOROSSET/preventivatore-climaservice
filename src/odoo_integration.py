import base64
import os
import xmlrpc.client


ODOO_REQUIRED_KEYS = ["ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_API_KEY"]


def odoo_settings():
    return {key: os.getenv(key, "").strip() for key in ODOO_REQUIRED_KEYS}


def odoo_configured():
    settings = odoo_settings()
    return all(settings.values())


def _server_url(base_url, path):
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


class OdooClient:
    def __init__(self, settings=None):
        self.settings = settings or odoo_settings()
        missing = [key for key, value in self.settings.items() if not value]
        if missing:
            raise ValueError("Configurazione Odoo incompleta: " + ", ".join(missing))
        self.url = self.settings["ODOO_URL"]
        self.db = self.settings["ODOO_DB"]
        self.username = self.settings["ODOO_USERNAME"]
        self.api_key = self.settings["ODOO_API_KEY"]
        self.common = xmlrpc.client.ServerProxy(_server_url(self.url, "/xmlrpc/2/common"), allow_none=True)
        self.models = xmlrpc.client.ServerProxy(_server_url(self.url, "/xmlrpc/2/object"), allow_none=True)
        self.uid = None

    def authenticate(self):
        if self.uid:
            return self.uid
        uid = self.common.authenticate(self.db, self.username, self.api_key, {})
        if not uid:
            raise PermissionError("Autenticazione Odoo non riuscita")
        self.uid = uid
        return uid

    def execute(self, model, method, args=None, kwargs=None):
        uid = self.authenticate()
        return self.models.execute_kw(
            self.db,
            uid,
            self.api_key,
            model,
            method,
            args or [],
            kwargs or {},
        )

    def read_opportunity(self, opportunity_id):
        records = self.execute(
            "crm.lead",
            "read",
            [[int(opportunity_id)]],
            {
                "fields": [
                    "id",
                    "name",
                    "partner_id",
                    "contact_name",
                    "email_from",
                    "phone",
                    "street",
                    "city",
                    "zip",
                ]
            },
        )
        if not records:
            return {}
        opportunity = records[0]
        partner_ref = opportunity.get("partner_id")
        if partner_ref:
            partner = self.read_partner(partner_ref[0])
            opportunity["partner"] = partner
        return opportunity

    def read_partner(self, partner_id):
        records = self.execute(
            "res.partner",
            "read",
            [[int(partner_id)]],
            {"fields": ["id", "name", "street", "city", "zip", "email", "phone"]},
        )
        return records[0] if records else {}

    def read_sale_order(self, order_id):
        records = self.execute(
            "sale.order",
            "read",
            [[int(order_id)]],
            {
                "fields": [
                    "id",
                    "name",
                    "partner_id",
                    "opportunity_id",
                    "amount_total",
                    "amount_untaxed",
                    "amount_tax",
                    "order_line",
                ]
            },
        )
        if not records:
            return {}

        order = records[0]
        partner_ref = order.get("partner_id")
        if partner_ref:
            order["partner"] = self.read_partner(partner_ref[0])

        line_ids = order.get("order_line") or []
        if line_ids:
            order["lines"] = self.read_sale_order_lines(line_ids)
        else:
            order["lines"] = []
        return order

    def read_sale_order_lines(self, line_ids):
        return self.execute(
            "sale.order.line",
            "read",
            [[int(line_id) for line_id in line_ids]],
            {
                "fields": [
                    "id",
                    "name",
                    "product_id",
                    "product_uom_qty",
                    "price_unit",
                    "price_subtotal",
                    "price_total",
                    "display_type",
                ]
            },
        )

    def create_attachment(self, *, res_model, res_id, filename, content, mimetype):
        attachment_id = self.execute(
            "ir.attachment",
            "create",
            [
                {
                    "name": filename,
                    "res_model": res_model,
                    "res_id": int(res_id),
                    "type": "binary",
                    "datas": base64.b64encode(content).decode("ascii"),
                    "mimetype": mimetype,
                }
            ],
        )
        return attachment_id

    def post_message_on_record(self, res_model, res_id, body, attachment_ids=None):
        return self.execute(
            res_model,
            "message_post",
            [[int(res_id)]],
            {
                "body": body,
                "attachment_ids": attachment_ids or [],
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_note",
            },
        )

    def post_message(self, opportunity_id, body, attachment_ids=None):
        return self.post_message_on_record("crm.lead", opportunity_id, body, attachment_ids)


def opportunity_to_prefill(opportunity):
    partner = opportunity.get("partner") or {}
    name = partner.get("name") or opportunity.get("contact_name") or opportunity.get("name") or ""
    street = partner.get("street") or opportunity.get("street") or ""
    city_parts = [partner.get("zip") or opportunity.get("zip") or "", partner.get("city") or opportunity.get("city") or ""]
    city = " ".join(part for part in city_parts if part).strip()
    return {
        "cliente": name,
        "indirizzo": street,
        "localita": city,
        "email": partner.get("email") or opportunity.get("email_from") or "",
        "telefono": partner.get("phone") or opportunity.get("phone") or "",
        "opportunita": opportunity.get("name") or "",
    }


def sale_order_to_prefill(order):
    partner = order.get("partner") or {}
    city_parts = [partner.get("zip") or "", partner.get("city") or ""]
    city = " ".join(part for part in city_parts if part).strip()
    opportunity_ref = order.get("opportunity_id") or []
    return {
        "cliente": partner.get("name") or "",
        "indirizzo": partner.get("street") or "",
        "localita": city,
        "email": partner.get("email") or "",
        "telefono": partner.get("phone") or "",
        "preventivo": order.get("name") or "",
        "opportunity_id": opportunity_ref[0] if opportunity_ref else "",
        "opportunita": opportunity_ref[1] if len(opportunity_ref) > 1 else "",
    }
