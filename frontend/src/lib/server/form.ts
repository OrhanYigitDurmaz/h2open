/** A text field, trimmed; "" when missing. */
export function text(data: FormData, name: string): string {
	const value = data.get(name);
	return typeof value === 'string' ? value.trim() : '';
}

/** A text field, or null when it is empty. */
export function optional(data: FormData, name: string): string | null {
	return text(data, name) || null;
}

/** A decimal typed with a comma or a dot ("12,50" → "12.50"). */
export function decimal(data: FormData, name: string): string {
	return text(data, name).replace(',', '.');
}
