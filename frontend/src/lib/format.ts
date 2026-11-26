import type { Money } from './api.js';

/** The currency new prices are entered in. */
export const CURRENCY = 'TRY';

const LOCALE = 'tr-TR';

export function formatMoney(money: Money): string {
	return new Intl.NumberFormat(LOCALE, { style: 'currency', currency: money.currency }).format(
		Number(money.amount)
	);
}

/** "20.00" → "20%" */
export function formatPercent(rate: string): string {
	return `${new Intl.NumberFormat(LOCALE).format(Number(rate))}%`;
}
