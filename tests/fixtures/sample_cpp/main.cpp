#include <iostream>

/**
 * A complex number class.
 */
class Complex {
public:
    double real;
    double imag;

    /** Constructor */
    Complex(double r, double i) : real(r), imag(i) {}

    /** Addition */
    Complex operator+(const Complex& other) {
        return Complex(real + other.real, imag + other.imag);
    }
private:
    void secret() {}
};

/**
 * Main entry point.
 */
int main() {
    Complex c1(1, 2), c2(3, 4);
    Complex c3 = c1 + c2;
    return 0;
}
