from dateutil.relativedelta import relativedelta
from datetime import datetime
from collections import defaultdict

from kardboard.models.kard import Kard
from kardboard.models.states import States
from kardboard.models.team import Team, TeamList
from kardboard.util import make_start_date, make_end_date, standard_deviation, average, median


def setup_teams(config):
    team_confs = config.get('CARD_TEAMS')
    teams = [Team(*args) for args in team_confs]
    team_list = TeamList(*teams)
    return team_list


class TeamStats(object):
    def __init__(self, team_name, exclude_classes=[]):
        self.team_name = team_name
        self.exclude_classes = exclude_classes
        self.card_info = []

    def oldest_card_date(self):
        query = Kard.objects.filter(
            team=self.team_name,
            _service_class__nin=self.exclude_classes,
            done_date__exists=True,
        ).order_by('done_date').only('done_date')
        oldest_card = query().first()

        if oldest_card is not None:
            return oldest_card.done_date
        else:
            return oldest_card

    def _card_info(self, card_qs):
        info = []
        if not hasattr(card_qs, '__iter__'):
            return info
        for card in card_qs:
            data = {}
            data['key'] = card.key
            data['cycle_time'] = card.cycle_time
            data['done_date'] = card.done_date
            data['service_class'] = card.service_class
            info.append(data)
        self.card_info = info
        return info

    def done_in_range(self, start_date, end_date):
        end_date = make_end_date(date=end_date)
        start_date = make_start_date(date=start_date)

        done = Kard.objects.filter(
            team=self.team_name,
            done_date__gte=start_date,
            done_date__lte=end_date,
            _service_class__nin=self.exclude_classes,
        )

        self._card_info(done)
        return done

    def cycle_times(self, weeks=4):
        start_date, end_date, weeks = self.throughput_date_range(weeks)
        cycle_time_list = self.done_in_range(start_date, end_date).values_list('_cycle_time')
        return [c for c in cycle_time_list if c is not None]

    def wip(self):
        states = States()
        wip = Kard.objects.filter(
            team=self.team_name,
            done_date=None,
            state__in=states.in_progress,
        )
        return wip

    def wip_count(self):
        return len(self.wip())

    def throughput_date_range(self, weeks=4):
        oldest_card_date = self.oldest_card_date()
        end_date = datetime.now()
        start_date = end_date - relativedelta(weeks=weeks)

        if oldest_card_date and start_date < oldest_card_date:
            start_date = oldest_card_date

        diff = end_date - start_date
        weeks = int(round(diff.days / 7.0))

        return (start_date, end_date, weeks)

    def weekly_throughput_ave(self, weeks=4):
        start_date, end_date, weeks = self.throughput_date_range(weeks)
        done = len(self.done_in_range(
            start_date, end_date))

        return int(round(done / float(weeks)))

    def monthly_throughput_ave(self, months=1):
        start_date, end_date, weeks = self.throughput_date_range(months * 4)

        months = int(round(weeks / 4.0))
        done = len(self.done_in_range(
            start_date, end_date))

        return int(round(done / float(months)))

    def lead_time(self, weeks=4):
        throughput = self.weekly_throughput_ave(weeks) / 7.0
        if throughput == 0:
            return float('nan')
        return int(round(self.wip_count() / throughput))

    def standard_deviation(self, weeks=4):
        stdev = standard_deviation(self.cycle_times(weeks))
        if stdev is not None:
            stdev = int(round(stdev))
        return stdev

    def average(self, weeks=4):
        ave = average(self.cycle_times(weeks))
        if ave is not None:
            ave = int(round(ave))
        return ave

    def median(self, weeks=4):
        med = median(self.cycle_times(weeks))
        if med is not None:
            med = int(round(med))
        return med

    def histogram(self, weeks=4):
        times = self.cycle_times(weeks)
        d = defaultdict(int)
        for t in times:
            d[t] += 1
        return dict(d)

    def percentile(self, target_pct, weeks=4):
        hist = self.histogram(weeks)
        total = sum(hist.values())
        pct_threshold = target_pct * total

        card_total = 0
        sorted_keys = hist.keys()
        sorted_keys.sort()
        for key in sorted_keys:
            cycle_time = key
            card_count = hist[key]
            card_total += card_count
            if card_total >= pct_threshold:
                return cycle_time
