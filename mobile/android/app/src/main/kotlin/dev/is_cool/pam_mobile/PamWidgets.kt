package dev.is_cool.pam_mobile

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.SharedPreferences
import android.view.View
import android.widget.RemoteViews
import es.antonborri.home_widget.HomeWidgetLaunchIntent
import es.antonborri.home_widget.HomeWidgetProvider

/** Shared plumbing: every PAM widget draws from numbers the app saved last time it was open and opens the app when tapped. */
abstract class PamWidget(private val layout: Int) : HomeWidgetProvider() {
    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray, widgetData: SharedPreferences) {
        for (id in appWidgetIds) {
            val v = RemoteViews(context.packageName, layout)
            val signedIn = widgetData.getString("signed_in", "0") == "1"
            v.setTextViewText(R.id.updated, if (signedIn) "Updated " + (widgetData.getString("updated", "") ?: "") else "")
            v.setOnClickPendingIntent(R.id.root, HomeWidgetLaunchIntent.getActivity(context, MainActivity::class.java))
            if (signedIn) bind(v, widgetData) else signedOut(v)
            appWidgetManager.updateAppWidget(id, v)
        }
    }

    abstract fun bind(v: RemoteViews, d: SharedPreferences)
    abstract fun signedOut(v: RemoteViews)
}

/** Today: what has been spent today and so far this month. */
class TodayWidget : PamWidget(R.layout.widget_today) {
    override fun bind(v: RemoteViews, d: SharedPreferences) {
        v.setTextViewText(R.id.title, "Spent today")
        v.setTextViewText(R.id.big, d.getString("today_spend", "\u20b90") ?: "")
        v.setTextViewText(R.id.sub, (d.getString("month_name", "") ?: "") + ": " + (d.getString("month_spend", "\u20b90") ?: ""))
    }
    override fun signedOut(v: RemoteViews) {
        v.setTextViewText(R.id.title, "PAM")
        v.setTextViewText(R.id.big, "Sign in")
        v.setTextViewText(R.id.sub, "Open the app to see today\u2019s spending")
    }
}

/** Budget: month spend against the sum of all limits, with a bar. */
class BudgetWidget : PamWidget(R.layout.widget_budget) {
    override fun bind(v: RemoteViews, d: SharedPreferences) {
        val pct = (d.getString("budget_pct", "0") ?: "0").toIntOrNull() ?: 0
        val has = d.getString("budget_total", "") != ""
        v.setTextViewText(R.id.title, "Budget \u00b7 " + (d.getString("month_name", "") ?: ""))
        v.setTextViewText(R.id.big, d.getString("month_spend", "\u20b90") ?: "")
        v.setTextViewText(R.id.sub, if (has) "of " + d.getString("budget_total", "") + " (" + pct + "%)" else "No limits set yet")
        v.setViewVisibility(R.id.bar, if (has) View.VISIBLE else View.GONE)
        v.setProgressBar(R.id.bar, 100, pct.coerceIn(0, 100), false)
    }
    override fun signedOut(v: RemoteViews) {
        v.setTextViewText(R.id.title, "PAM budget")
        v.setTextViewText(R.id.big, "Sign in")
        v.setTextViewText(R.id.sub, "Open the app")
        v.setViewVisibility(R.id.bar, View.GONE)
    }
}

/** Bills: the next three payments due. */
class BillsWidget : PamWidget(R.layout.widget_bills) {
    override fun bind(v: RemoteViews, d: SharedPreferences) {
        v.setTextViewText(R.id.title, "Coming up")
        val rows = intArrayOf(R.id.row1, R.id.row2, R.id.row3)
        var any = false
        for (i in 0..2) {
            val t = d.getString("bill_" + (i + 1), "") ?: ""
            v.setTextViewText(rows[i], t)
            v.setViewVisibility(rows[i], if (t.isEmpty()) View.GONE else View.VISIBLE)
            if (t.isNotEmpty()) any = true
        }
        v.setTextViewText(R.id.empty, "Nothing due in the next 30 days")
        v.setViewVisibility(R.id.empty, if (any) View.GONE else View.VISIBLE)
    }
    override fun signedOut(v: RemoteViews) {
        v.setTextViewText(R.id.title, "PAM bills")
        for (r in intArrayOf(R.id.row1, R.id.row2, R.id.row3)) v.setViewVisibility(r, View.GONE)
        v.setTextViewText(R.id.empty, "Sign in to see what is due")
        v.setViewVisibility(R.id.empty, View.VISIBLE)
    }
}
