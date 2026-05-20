/**
 * Sample TypeScript module used by codexa tests.
 */

export const VERSION: string = "1.0.0";

/**
 * Add two numbers.
 */
export function add(a: number, b: number = 0): number {
    return a + b;
}

export const multiply = (a: number, b: number): number => a * b;

function notExported(): void {}

/**
 * A small greeter.
 */
export class Greeter {
    private name: string;

    constructor(name: string) {
        this.name = name;
    }

    /**
     * Greet by name.
     */
    greet(): string {
        return `hello ${this.name}`;
    }

    _privateMethod(): void {}
}

export interface Point {
    x: number;
    y: number;
}

export type Pair = [number, number];

/**
 * Fetch items with optional filters.
 */
export async function fetchItems(id: string, since?: string, limit?: number): Promise<string[]> {
    return [];
}
