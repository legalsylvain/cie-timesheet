# Copyright 2020 Coop IT Easy SCRLfs
#   - Vincent Van Rossem <vincent@coopiteasy.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from datetime import date, datetime, timedelta

from pytz import timezone

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

OVERTIME_WRITE_ACCESS_GROUPS = ("hr.group_hr_user", "hr.group_hr_manager")


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Numeric fields
    current_day_working_hours = fields.Float(
        "Current Day Working Hours",
        compute="_compute_current_day_working_hours",
        help="Hours to work for the current day",
    )
    initial_overtime = fields.Float(
        string="Initial Overtime",
        default=0.0,
        help="Initial Overtime to start Overtime Start Date with",
    )
    total_overtime = fields.Float(
        string="Total Overtime",
        compute="_compute_total_overtime",
        help="Total Overtime since Overtime Start Date",
    )
    timesheet_sheet_ids = fields.One2many(
        comodel_name="hr_timesheet.sheet",
        inverse_name="employee_id",
        string="Timesheet sheets",
    )

    # Date fields
    overtime_start_date = fields.Date(
        string="Overtime Start Date",
        required=True,
        default=date.today().replace(month=1, day=1),
        help="Overtime Start Date to compute overtime",
    )

    _has_overtime_access = fields.Boolean(
        string="Has access to overtime page",
        compute="_compute_has_overtime_access",
    )

    @api.multi
    def get_working_hours(self, start_date, end_date=None):
        """
        Get the working hours for a given date range according to the
        employee's contracts
        @param start_date: date
        @param end_date: date
        @return: total of working hours
        """
        self.ensure_one()
        if end_date is None:
            end_date = start_date
        tz = timezone(self.tz)
        start_dt = tz.localize(
            datetime(start_date.year, start_date.month, start_date.day)
        )
        end_dt = tz.localize(
            datetime(end_date.year, end_date.month, end_date.day)
        ) + timedelta(days=1)
        work_time_per_day = self.list_normal_work_time_per_day(start_dt, end_dt)
        # .list_normal_work_time_per_day() returns a list of tuples:
        # (date, work time)
        return sum(work_time[1] for work_time in work_time_per_day)

    @api.multi
    def _compute_current_day_working_hours(self):
        """
        Computes working hours for the current day according to the employee's
        contracts.
        """
        current_day = date.today()
        for employee in self:
            employee.current_day_working_hours = employee.get_working_hours(current_day)

    @api.multi
    def _compute_has_overtime_access(self):
        for rec in self:
            has_access = False
            if self._has_overtime_write_access():
                has_access = True
            elif rec.user_id == self.env.user:
                has_access = True
            else:
                subordinates = self.env["hr.employee"].search(
                    [
                        (
                            "id",
                            "child_of",
                            self.env.user.employee_ids.mapped("id"),
                        )
                    ]
                )
                has_access = rec in subordinates
            rec._has_overtime_access = has_access

    @api.multi
    @api.depends("timesheet_sheet_ids.active")
    def _compute_total_overtime(self):
        """
        Computes total overtime since employee's overtime start date
        """
        for employee in self:
            sheets = self.env["hr_timesheet.sheet"].search(
                [
                    ("employee_id", "=", employee.id),
                    ("date_end", ">=", employee.overtime_start_date),
                ]
            )
            overtime = sum(sheet.timesheet_overtime for sheet in sheets)
            employee.total_overtime = employee.initial_overtime + overtime

    def _has_overtime_write_access(self):
        for group in OVERTIME_WRITE_ACCESS_GROUPS:
            if self.env.user.has_group(group):
                return True
        return False

    def write(self, vals):
        for restricted_field in ["initial_overtime", "overtime_start_date"]:
            if (
                restricted_field in vals
                and self[restricted_field] != vals[restricted_field]
                and not self._has_overtime_write_access()
            ):
                raise AccessError(
                    _("You do not have the permission to modify this field.")
                )

        return super(HrEmployee, self).write(vals)
