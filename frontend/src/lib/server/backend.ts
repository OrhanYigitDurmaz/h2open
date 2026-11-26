// Calls to the h2open API, made from this server with the login token kept
// in an httpOnly cookie, so the token never reaches browser JavaScript.

import { error, redirect, type RequestEvent } from '@sveltejs/kit';
import { BACKEND_URL } from '$app/env/private';

export const SESSION_COOKIE = 'h2open_session';

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

/** A request the backend refused, with a message fit to show the user. */
export class BackendError extends Error {
	constructor(
		readonly status: number,
		message: string,
		/** Message per field (dotted path, e.g. "container.quantity"). */
		readonly fields: Readonly<Record<string, string>> = {}
	) {
		super(message);
	}
}

/** Send a request and return the raw response; 503 if the backend is down. */
export async function send(
	fetch: RequestEvent['fetch'],
	method: Method,
	path: string,
	{ token, body }: { token?: string | null; body?: unknown } = {}
): Promise<Response> {
	const headers: Record<string, string> = { accept: 'application/json' };
	if (token) headers.authorization = `Bearer ${token}`;
	if (body !== undefined) headers['content-type'] = 'application/json';
	try {
		return await fetch(`${BACKEND_URL}${path}`, {
			method,
			headers,
			body: body === undefined ? undefined : JSON.stringify(body)
		});
	} catch {
		error(503, 'The h2open server cannot be reached.');
	}
}

/**
 * Call the backend as the logged-in user.
 *
 * An expired login sends the user to the login page; any other refusal
 * throws a {@link BackendError}.
 */
export async function backend<T>(
	event: RequestEvent,
	method: Method,
	path: string,
	body?: unknown
): Promise<T> {
	const response = await send(event.fetch, method, path, { token: event.locals.token, body });
	if (response.status === 401) {
		event.cookies.delete(SESSION_COOKIE, { path: '/' });
		redirect(303, '/login');
	}
	if (!response.ok) throw await toError(response);
	if (response.status === 204) return undefined as T;
	return (await response.json()) as T;
}

/** Like {@link backend}, for `load`: a refusal becomes the error page. */
export async function get<T>(event: RequestEvent, path: string): Promise<T> {
	try {
		return await backend<T>(event, 'GET', path);
	} catch (e) {
		if (e instanceof BackendError) error(e.status, e.message);
		throw e;
	}
}

interface ValidationIssue {
	loc: (string | number)[];
	msg: string;
}

async function toError(response: Response): Promise<BackendError> {
	const body: unknown = await response.json().catch(() => null);
	if (response.status === 422 && hasIssues(body)) {
		const fields: Record<string, string> = {};
		for (const issue of body.detail) {
			const key = issue.loc.slice(1).join('.');
			fields[key] ??= issue.msg;
		}
		return new BackendError(422, 'Some fields need fixing.', fields);
	}
	if (response.status === 403) return new BackendError(403, 'You are not allowed to do that.');
	if (hasDetail(body)) return new BackendError(response.status, sentence(body.detail));
	return new BackendError(response.status, `The server answered ${response.status}.`);
}

function hasIssues(body: unknown): body is { detail: ValidationIssue[] } {
	return (
		typeof body === 'object' && body !== null && 'detail' in body && Array.isArray(body.detail)
	);
}

function hasDetail(body: unknown): body is { detail: string } {
	return (
		typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string'
	);
}

/** "the barcode is already used" → "The barcode is already used." */
function sentence(text: string): string {
	const capitalized = text.charAt(0).toUpperCase() + text.slice(1);
	return /[.!?]$/.test(capitalized) ? capitalized : `${capitalized}.`;
}
