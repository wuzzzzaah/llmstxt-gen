/**
 * Package-level Javadoc for sample_java.
 */
package sample_java;

import java.util.List;

/**
 * A public class with Javadoc.
 */
public class SampleClass {
    /**
     * A public field.
     */
    public String publicField;

    /**
     * A private field.
     */
    private int privateField;

    /**
     * Constructor for SampleClass.
     * @param publicField the field value
     */
    public SampleClass(String publicField) {
        this.publicField = publicField;
    }

    /**
     * A public method.
     * @param input the input string
     * @return the same string
     */
    public String publicMethod(String input) {
        return input;
    }

    /**
     * A private method.
     */
    private void privateMethod() {
    }

    /**
     * A protected method.
     */
    protected void protectedMethod() {
    }

    /**
     * A package-private method.
     */
    void packagePrivateMethod() {
    }

    /**
     * An inner class.
     */
    public static class InnerClass {
        public void innerMethod() {}
    }
}

/**
 * A public interface.
 */
interface SampleInterface {
    /**
     * Interface method.
     */
    void doSomething();
}

/**
 * A public enum.
 */
public enum SampleEnum {
    VALUE1, VALUE2
}

/**
 * A public record.
 * @param name the name
 * @param age the age
 */
public record SampleRecord(String name, int age) {
}

/**
 * A method using generics.
 */
class GenericClass<T extends Comparable<T>> {
    public <U> List<U> genericMethod(U input) {
        return List.of(input);
    }
}

/**
 * A method with annotations.
 */
class AnnotatedClass {
    @Deprecated
    @SuppressWarnings("unchecked")
    public void annotatedMethod() {
    }
}
