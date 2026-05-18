using System;

namespace SampleCsharp
{
    /// <summary>
    /// A public class with XML docs.
    /// </summary>
    public class PublicClass
    {
        /// <summary>
        /// A public property.
        /// </summary>
        public string Name { get; set; }

        /// <summary>
        /// A public method with an attribute.
        /// </summary>
        [Obsolete("Use something else")]
        public void DoSomething() {}

        /// <summary>
        /// A generic method with a constraint.
        /// </summary>
        public T Identity<T>(T val) where T : class
        {
            return val;
        }

        protected void ProtectedMethod() {}

        private void PrivateMethod() {}
    }

    public interface IService
    {
        void Run();
    }

    public enum Status
    {
        Active,
        Inactive
    }

    public record User(string Id, string Email);

    public struct Point
    {
        public int X;
        public int Y;
    }

    public partial class PartialClass
    {
        public void Part1() {}
    }

    public partial class PartialClass
    {
        public void Part2() {}
    }
}
